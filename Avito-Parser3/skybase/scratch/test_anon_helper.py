from curl_cffi.requests import Session

def is_anonymous_proxy(proxy: str, my_ip: str = "62.183.2.72", timeout: float = 3.0) -> bool:
    try:
        clean = proxy.strip()
        if clean.startswith("socks5://"):
            clean = "socks5h://" + clean[9:]
        with Session(impersonate="safari15_5", proxy=clean, timeout=timeout, verify=False) as s:
            r = s.get("http://icanhazip.com", timeout=timeout)
            if r.status_code == 200:
                ret_ip = r.text.strip()
                if my_ip and my_ip in ret_ip:
                    print(f"Proxy {proxy} LEAKS HOST IP: {ret_ip}")
                    return False
                print(f"Proxy {proxy} OK anonymous IP: {ret_ip}")
                return True
    except Exception as e:
        print(f"Proxy {proxy} failed echo: {e}")
    return False

# Test with a dummy or real proxy
print("Function defined and ready.")
