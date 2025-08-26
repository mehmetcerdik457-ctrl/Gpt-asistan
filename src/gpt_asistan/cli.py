import argparse, asyncio, os, sys
from . import memory
from .provider import call_openai, offline_reply

def main():
    p=argparse.ArgumentParser(description="Hafif GPT Asistan CLI")
    p.add_argument("-s","--session", default="default")
    p.add_argument("message", nargs="*")
    args=p.parse_args()
    message=" ".join(args.message).strip()
    if not message:
        print("Kullanım: ga \"mesajın\""); sys.exit(1)
    memory.init()
    memory.add(args.session,"user",message)
    hist = memory.history(args.session, limit=30)
    reply = asyncio.run(call_openai(hist)) or offline_reply(hist)
    memory.add(args.session,"assistant",reply)
    print(reply)

if __name__ == "__main__":
    main()
