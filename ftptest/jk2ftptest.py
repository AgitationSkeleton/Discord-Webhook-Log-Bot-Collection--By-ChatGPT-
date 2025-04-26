import requests

# Your FastDL URL
fastdl_base = "https://redchanit.xyz/redchanitfastdl_quake/jk2/base/"

# List of pk3s you expect to be downloadable
pk3_files = [
    "dotf.pk3",
    "link.pk3",
    "p3po.pk3",
]

# Check each file
for pk3 in pk3_files:
    url = fastdl_base + pk3
    try:
        response = requests.head(url, timeout=5, allow_redirects=True)
        if response.status_code == 200:
            print(f"[✓] {pk3} is available")
        else:
            print(f"[X] {pk3} not found (status {response.status_code})")
    except requests.RequestException as e:
        print(f"[X] {pk3} error: {e}")
