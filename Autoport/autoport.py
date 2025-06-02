import miniupnpc
import datetime
import time
import pytz
import schedule

PST = pytz.timezone("America/Los_Angeles")
PORT_LIST_PATH = "portmap.txt"

def load_ports():
    ports = []
    with open(PORT_LIST_PATH, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                port = int(line)
                ports.append(port)
            except ValueError:
                print(f"Skipping invalid line: {line}")
    return ports

def forward_ports():
    print("Running port forwarding check...")
    upnp = miniupnpc.UPnP()
    upnp.discoverdelay = 200
    upnp.discover()
    upnp.selectigd()

    internal_ip = upnp.lanaddr
    print(f"Using internal IP: {internal_ip}")

    existing = set()
    for i in range(64):
        try:
            entry = upnp.getgenericportmapping(i)
            if entry:
                proto, ext_port = entry[0], int(entry[1])
                existing.add((proto.upper(), ext_port))
        except Exception:
            break

    for port in load_ports():
        for proto in ["TCP", "UDP"]:
            if (proto, port) not in existing:
                try:
                    upnp.addportmapping(port, proto, internal_ip, port, f"AutoPortMap-{proto}", "")
                    print(f"Forwarded {proto} port {port} to {internal_ip}")
                except Exception as e:
                    print(f"Failed to forward {proto} port {port}: {e}")
            else:
                print(f"{proto} port {port} already forwarded; skipping.")

def schedule_job():
    def job():
        now = datetime.datetime.now(PST)
        print(f"[{now.isoformat()}] Scheduled hourly port check running.")
        forward_ports()

    # Run hourly at :00
    schedule.every().hour.at(":00").do(job)

    # Run immediately on launch
    print(f"[{datetime.datetime.now(PST).isoformat()}] Initial port check running.")
    forward_ports()

    print("Hourly port forwarding job scheduled (every hour on the hour PST).")
    while True:
        schedule.run_pending()
        time.sleep(30)

if __name__ == "__main__":
    schedule_job()
