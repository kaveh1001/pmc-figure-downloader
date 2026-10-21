# PMC Figure Downloader - server prototype

Docker-hosted web service. ImageMagick runs inside the server container, not on visitors' machines.

## Run

```sh
docker build -t pmc-downloader .
docker run --rm -p 8000:8000 pmc-downloader
```

Open http://localhost:8000 and paste a PMC tiled-viewer URL.

## Status and limitations

This is an **untested prototype**, not yet a public production service. The provided PMC Figure 1 URL is prefilled. The live PMC endpoint, its manifest structure and returned tile order still need end-to-end verification. The service has no user authentication, rate limits, job queue, asynchronous progress display, or hosting configuration. Public deployment requires these safeguards, request quotas, output-size limits, cleanup policy and assessment of PMC usage requirements. Long-running downloads may exceed hosting request timeouts. Non-tiled images are not supported.
