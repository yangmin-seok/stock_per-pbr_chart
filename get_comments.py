import requests
import json

try:
    c = requests.get('https://api.github.com/repos/sharebook-kr/pykrx/issues/276/comments').json()
    with open('comments.txt','w',encoding='utf-8') as f:
        f.write(json.dumps([x.get('body', '') for x in c if isinstance(x, dict)], ensure_ascii=False, indent=2))
except Exception as e:
    pass
