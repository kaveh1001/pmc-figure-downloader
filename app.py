import io, os, re, zipfile, tempfile, subprocess, concurrent.futures
from urllib.parse import urlparse, parse_qs
import requests
from flask import Flask, request, send_file, render_template_string

app = Flask(__name__)
BASE = 'https://www.ncbi.nlm.nih.gov/corecgi/tileshop/tileshop.fcgi'
HEADERS = {'User-Agent': 'Mozilla/5.0 PMC-Figure-Downloader/0.1'}
HTML = '''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PMC Figure Downloader</title>
<style>
body{font:17px system-ui;max-width:720px;margin:5vh auto;padding:20px;line-height:1.5}
input,button{font:inherit;box-sizing:border-box;padding:12px;width:100%;margin:6px 0 20px}
button{background:#164b83;color:white;border:0;border-radius:6px;cursor:pointer}
label{font-weight:600}.note{color:#555}.error{color:#a00}
footer{border-top:1px solid #ddd;margin-top:32px;padding-top:12px;font-size:14px;color:#555}
</style>
</head>
<body>
<h1>PMC High-Resolution Figure Downloader</h1>
<p>Download full-resolution PMC figures as PNGs, without installing software.</p>
<ol>
<li>Open a figure in the PMC zoom viewer and copy its URL.</li>
<li>Paste the URL below and enter figures: <strong>1</strong>, <strong>1-3</strong>, or <strong>1-</strong> for all available.</li>
<li>Click <strong>Download PNG ZIP</strong>.</li>
</ol>
{% if error %}<p class="error">{{error}}</p>{% endif %}
<form method="post" action="/download">
<label for="url">PMC tiled viewer URL</label>
<input id="url" name="url" required value="{{url}}">
<label for="figures">Figure numbers</label>
<input id="figures" name="figures" required value="{{figures}}">
<p class="note">Examples: 1 3 4, 2-6, 1- (up to 100, stops after 3 missing figures)</p>
<button type="submit">Download PNG ZIP</button>
</form>
<p class="note">Tiled figures only. Processing may take a few minutes. Please respect PMC and article licensing terms.</p>
<footer>Created by Kaveh Bazargan</footer>
</body>
</html>'''

class MissingFigure(Exception): pass

def parse_url(url):
    url = url.replace('&amp;', '&').replace('\\&', '&')
    u = urlparse(url)
    if u.scheme != 'https' or u.hostname != 'www.ncbi.nlm.nih.gov' or not u.path.endswith('/tileshop_pmc_inline.html'):
        raise ValueError('Please provide an NCBI PMC tiled-viewer URL.')
    q = parse_qs(u.query)
    image = q.get('id', [''])[0]
    pool = q.get('p', ['PMC3'])[0]
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,180}', image) or not re.fullmatch(r'PMC\d+', pool):
        raise ValueError('Invalid image ID or pool.')
    m = re.match(r'^(.*?[Ff]ig)(\d+)(_HTML\.[A-Za-z0-9]+)$', image, re.I) or re.match(r'^(.*?f)(\d+)(\.[A-Za-z0-9]+)$', image, re.I) or re.match(r'^(.*?)(\d{4})(\.[A-Za-z0-9]+)$', image)
    if not m: raise ValueError('Cannot identify the figure number from this image ID.')
    return pool, m.group(1), m.group(3), len(m.group(2))

def tokens(s):
    result = []
    for t in s.split():
        if re.fullmatch(r'\d+-\d+', t):
            a,b=map(int,t.split('-'))
            if a<1 or b<a or b-a>99: raise ValueError('Invalid figure range.')
            result.extend(range(a,b+1))
        elif re.fullmatch(r'\d+-', t):
            result.append(('open',int(t[:-1])))
        elif re.fullmatch(r'\d+', t): result.append(int(t))
        else: raise ValueError('Invalid figure selection.')
    if not result or len(result)>100 or any(isinstance(x,int) and not 1<=x<=9999 for x in result): raise ValueError('Choose 1 to 100 valid figures.')
    return result

def fetch(session, params, timeout=40):
    r=session.get(BASE,params=params,headers=HEADERS,timeout=timeout)
    if r.status_code in (404,410): raise MissingFigure()
    r.raise_for_status()
    return r.content

def get_manifest(session,pool,image):
    raw=fetch(session,{'manifest':1,'p':pool,'id':image,'w':1000,'h':800}).decode('utf-8','replace')
    sat=re.search(r'\bSat\s*:\s*["\']?([\w.-]+)',raw)
    views=re.search(r'\baView\s*:\s*\[(.*?)\]',raw,re.S)
    if not sat or not views: raise MissingFigure()
    options=[]
    for obj in re.findall(r'\{([^{}]*)\}',views.group(1)):
        fields=dict(re.findall(r'\b(sId|W|H|w|h)\s*:\s*["\']?([\w.-]+)',obj))
        if all(k in fields for k in ('sId','W','H','w','h')):
            try:
                W,H,w,h=(int(fields[k]) for k in ('W','H','w','h'))
                if min(W,H,w,h)>0 and W*H<=250_000_000: options.append((W*H,fields['sId'],W,H,w,h))
            except ValueError: pass
    if not options: raise MissingFigure()
    _,sid,W,H,w,h=max(options)
    cols=(W+w-1)//w; rows=(H+h-1)//h
    if cols*rows>1000: raise ValueError('Too many image tiles.')
    return sat.group(1),sid,W,H,cols,rows

def tile(args):
    pool,sid,sat,r,c=args
    for attempt in range(3):
        try:
            with requests.Session() as s:
                data=fetch(s,{'p':pool,'id':sid,'s':sat,'r':r,'c':c},90)
            if not data.startswith(b'\xff\xd8'): raise ValueError('Invalid JPEG tile')
            return (r,c,data)
        except Exception:
            if attempt==2: raise

def build_figure(pool,prefix,ext,width,n,folder):
    image=f'{prefix}{n:0{width}d}{ext}'
    with requests.Session() as s: sat,sid,W,H,cols,rows=get_manifest(s,pool,image)
    work=os.path.join(folder,f'fig{n}')
    os.mkdir(work)
    tasks=[(pool,sid,sat,r,c) for r in range(1,rows+1) for c in range(1,cols+1)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        for r,c,data in ex.map(tile,tasks):
            with open(os.path.join(work,f'tile_{r}_{c}.jpg'),'wb') as f:f.write(data)
    rowfiles=[]
    for r in range(1,rows+1):
        row=os.path.join(work,f'row_{r}.png')
        subprocess.run(['magick',*[os.path.join(work,f'tile_{r}_{c}.jpg') for c in range(1,cols+1)],'+append',row],check=True,timeout=120)
        rowfiles.append(row)
    out=os.path.join(folder,f'fig{n}.png')
    subprocess.run(['magick',*rowfiles,'-append','-gravity','NorthWest','-crop',f'{W}x{H}+0+0','+repage',out],check=True,timeout=180)
    return out

@app.get('/')
def home():return render_template_string(HTML,url='https://www.ncbi.nlm.nih.gov/core/lw/2.0/html/tileshop_pmc/tileshop_pmc_inline.html?title=Click%20on%20image%20to%20zoom&p=PMC3&id=13085302_13046_2026_3695_Fig1_HTML.jpg',figures='1',error=None)

@app.post('/download')
def download():
    url=request.form.get('url',''); selection=request.form.get('figures','')
    try:
        pool,prefix,ext,width=parse_url(url)
        choices=tokens(selection)
        archive=io.BytesIO(); completed=[]; failures=[]; seen=set()
        with tempfile.TemporaryDirectory() as folder, zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=4) as z:
            for choice in choices:
                if isinstance(choice,tuple):
                    candidates=range(choice[1],min(choice[1]+100,10000)); open_range=True
                else: candidates=[choice];open_range=False
                missing=0
                for n in candidates:
                    if n in seen:continue
                    seen.add(n)
                    try:
                        path=build_figure(pool,prefix,ext,width,n,folder)
                        z.write(path,os.path.basename(path));completed.append(n);missing=0
                    except MissingFigure:
                        if open_range:
                            missing+=1
                            if missing>=3:break
                        else:failures.append(f'Figure {n}: not found')
                    except Exception as e:
                        failures.append(f'Figure {n}: {type(e).__name__}: {str(e)[:160]}')
                        if open_range:break
            z.writestr('download_report.txt',f'Downloaded: {len(completed)}\nFigures: {completed}\nFailures: {failures}\n')
        if not completed:raise ValueError('No figures could be downloaded. '+('; '.join(failures[:2])))
        archive.seek(0)
        return send_file(archive,mimetype='application/zip',as_attachment=True,download_name='PMC_figures.zip')
    except Exception as e:
        return render_template_string(HTML,url=url,figures=selection,error=str(e)),400

if __name__=='__main__':app.run(host='0.0.0.0',port=int(os.environ.get('PORT','8000')))
