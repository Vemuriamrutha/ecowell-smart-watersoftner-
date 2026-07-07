"""Quick endpoint checker using urllib (no external deps)"""
import urllib.request, json

ENDPOINTS = [
    ("GET", "http://localhost:8000/health",       None),
    ("GET", "http://localhost:8000/telemetry",    None),
    ("GET", "http://localhost:8000/events",       None),
    ("GET", "http://localhost:8000/alerts",       None),
    ("GET", "http://localhost:8000/health-score", None),
    ("GET", "http://localhost:8000/dashboard",    None),
    ("POST","http://localhost:8000/command",      b'{"command":"regenerate"}'),
    ("POST","http://localhost:8000/command",      b'{"command":"HACK_DEVICE"}'),
]

all_pass = True
for method, url, body in ENDPOINTS:
    try:
        req = urllib.request.Request(url, data=body, method=method)
        req.add_header("Content-Type","application/json")
        with urllib.request.urlopen(req, timeout=4) as r:
            data = json.loads(r.read())
            short = str(data)[:90]
            path = url.replace("http://localhost:8000","")
            print(f"PASS {method} {path}")
            print(f"     -> {short}")
    except urllib.error.HTTPError as e:
        data = json.loads(e.read())
        path = url.replace("http://localhost:8000","")
        if e.code == 400 and body and b"HACK" in body:
            print(f"PASS {method} {path} (rejected with 400 as expected)")
            print(f"     -> {data}")
        else:
            print(f"FAIL {method} {path} HTTP {e.code} -> {data}")
            all_pass = False
    except Exception as e:
        path = url.replace("http://localhost:8000","")
        print(f"FAIL {method} {path} -> {e}")
        all_pass = False

print()
print("ALL ENDPOINTS PASSED" if all_pass else "SOME ENDPOINTS FAILED")
