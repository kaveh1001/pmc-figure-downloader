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
<title>PMC High-Resolution Figure Downloader</title>
<style>
:root{color-scheme:light}body{font:16px/1.55 system-ui,-apple-system,sans-serif;max-width:820px;margin:28px auto;padding:0 20px 36px;color:#182334;background:#fff}h1{font-size:clamp(26px,4vw,34px);line-height:1.2;margin-bottom:12px}h2{font-size:21px;margin:26px 0 10px}p{margin:10px 0}a{color:#14558e}a:hover{text-decoration:none}.intro{font-size:17px}.note{color:#536174;font-size:14px}.error{color:#a00;background:#fff0f0;padding:10px;border-radius:6px}.examples{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:16px 0}.example{border:1px solid #d9e0e8;border-radius:10px;overflow:hidden}.example svg{display:block;width:100%;height:auto;background:#edf3f8}.example .inside{padding:12px}.example p{font-size:14px;margin:5px 0}.supported{color:#167247}.unsupported{color:#775b37}form{padding:20px;border:1px solid #d5e0ed;background:#f7faff;border-radius:10px;margin:18px 0}label{display:block;font-weight:650;margin-top:10px}input,button{font:inherit;box-sizing:border-box;padding:11px;width:100%;margin:5px 0 10px;border-radius:6px}input{border:1px solid #9eafc0}button{background:#164b83;color:white;border:0;cursor:pointer;font-weight:650;margin-top:10px}button:hover{background:#103e6c}table{border-collapse:collapse;width:100%;font-size:15px}th,td{text-align:left;border-bottom:1px solid #e2e7ed;padding:7px 10px}th{background:#f3f6fa}td:first-child{white-space:nowrap;width:30%}code{background:#eef2f7;padding:2px 5px;border-radius:4px}ol{padding-left:24px}footer{border-top:1px solid #ddd;margin-top:28px;padding-top:14px;font-size:14px;color:#536174}@media(max-width:540px){.examples{grid-template-columns:1fr}body{padding:0 14px}form{padding:14px}}
</style>
</head>
<body>
<h1>PMC High-Resolution Figure Downloader</h1>
<p class="intro">Some figures in PubMed Central (PMC) are divided into <strong>hundreds of small image tiles</strong>. This lets readers zoom smoothly into large images without downloading the entire figure.</p>
<p><strong>The tiled version is often the highest-resolution version available through PMC.</strong> This free tool retrieves the tiles and assembles them into a single high-resolution PNG.</p>
<p class="note">No installation required. Works on Mac, Windows, Linux and mobile devices with a modern browser.</p>
<h2>Tiled versus non-tiled figures</h2>
<div class="examples">
  <div class="example">
    <svg viewBox="0 0 360 175" role="img" aria-label="Illustration of a scientific figure divided into many small image tiles">
      <defs><linearGradient id="tilebg" x2="1" y2="1"><stop stop-color="#e1edf8"/><stop offset="1" stop-color="#a4c1d8"/></linearGradient></defs>
      <rect width="360" height="175" fill="url(#tilebg)"/><g fill="none" stroke="#496b87" stroke-width="2"><path d="M15 143 Q60 120 85 77 T157 85 T230 51 T342 39"/><path d="M16 122 Q60 146 100 118 T190 106 T290 80 T345 106"/></g>
      <g stroke="#fff" stroke-width="1" opacity=".9"><path d="M36 0V175 M72 0V175 M108 0V175 M144 0V175 M180 0V175 M216 0V175 M252 0V175 M288 0V175 M324 0V175"/><path d="M0 35H360 M0 70H360 M0 105H360 M0 140H360"/></g>
      <rect x="12" y="10" width="116" height="26" rx="5" fill="#fff" opacity=".95"/><text x="22" y="28" font-size="13" fill="#173b59">Many image tiles</text>
    </svg>
    <div class="inside"><strong class="supported">Tiled figure — Supported</strong><p>Opens in PMC's interactive zoom viewer.</p><a href="https://www.ncbi.nlm.nih.gov/core/lw/2.0/html/tileshop_pmc/tileshop_pmc_inline.html?title=Click%20on%20image%20to%20zoom&amp;p=PMC3&amp;id=13085302_13046_2026_3695_Fig1_HTML.jpg" target="_blank" rel="noopener">View PMC example ↗</a></div>
  </div>
  <div class="example">
    <svg viewBox="0 0 360 175" role="img" aria-label="Illustration of a single non-tiled scientific figure image">
      <rect width="360" height="175" fill="#edf3f8"/><rect x="38" y="13" width="284" height="149" rx="5" fill="#c6d8e5" stroke="#9cb5c8"/><g fill="none" stroke="#496b87" stroke-width="2"><path d="M49 140 Q90 116 116 76 T186 86 T258 51 T312 41"/><path d="M49 122 Q96 147 135 117 T218 107 T309 89"/></g><rect x="49" y="22" width="113" height="26" rx="5" fill="#fff" opacity=".95"/><text x="59" y="40" font-size="13" fill="#173b59">Single image</text>
    </svg>
    <div class="inside"><strong class="unsupported">Non-tiled figure — Not supported</strong><p>Delivered as an ordinary image file.</p><a href="https://pmc.ncbi.nlm.nih.gov/articles/PMC2587244/figure/F3/" target="_blank" rel="noopener">View PMC example ↗</a></div>
  </div>
</div>
<h2>Download figures</h2>
{% if error %}<p class="error">{{error}}</p>{% endif %}
<form method="post" action="/download">
  <label for="url">PMC tiled-viewer URL</label>
  <input id="url" name="url" required value="{{url}}" aria-describedby="url-help">
  <p id="url-help" class="note">Open a figure in PMC's tiled zoom viewer and copy the address from your browser.</p>
  <label for="figures">Figure numbers</label>
  <input id="figures" name="figures" required value="{{figures}}" aria-describedby="fig-help">
  <p id="fig-help" class="note">Examples: <code>1 3 5</code>, <code>2-5</code>, <code>3-</code>, <code>1-3 5 7-9</code></p>
  <button type="submit">Download PNG ZIP</button>
</form>
<h2>How to use</h2>
<ol><li>Open a PMC figure in its tiled zoom viewer.</li><li>Copy the viewer URL and paste it above.</li><li>Specify the figures you want using the examples below.</li><li>Click <strong>Download PNG ZIP</strong>.</li></ol>
<h2>Selecting figures</h2>
<table><thead><tr><th>Enter</th><th>Downloads</th></tr></thead><tbody>
<tr><td><code>3</code></td><td>Figure 3</td></tr>
<tr><td><code>1 3 5</code></td><td>Figures 1, 3 and 5</td></tr>
<tr><td><code>2-5</code></td><td>Figures 2 through 5</td></tr>
<tr><td><code>3-</code></td><td>Figure 3 and all following available figures</td></tr>
<tr><td><code>1-</code></td><td>All available figures from Figure 1</td></tr>
<tr><td><code>1-3 5 7-9</code></td><td>Figures 1, 2, 3, 5, 7, 8 and 9</td></tr>
<tr><td><code>1 3 5-</code></td><td>Figures 1 and 3, then Figure 5 onwards</td></tr>
</tbody></table>
<p class="note">Separate selections with spaces. Combine individual numbers, ranges and open-ended ranges. Open-ended ranges stop after three consecutive missing figures (maximum 100 attempted numbers).</p>
<p class="note">The ZIP contains reconstructed PNG figures and a download report. Only supported PMC tiled-viewer figures can be reconstructed. Please respect the applicable article and figure licences. Processing may take a few minutes.</p>
<footer>Created by <strong>Kaveh Bazargan</strong> · <a href="mailto:kaveh1000@gmail.com">kaveh1000@gmail.com</a></footer>
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
