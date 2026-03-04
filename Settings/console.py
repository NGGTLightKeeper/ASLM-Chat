import json
import datetime
from .settings import *

class PrintTechData:
    def PTD_Print(self):
        print("------------------------------------------------------")
        try:
            json_path = BASE_DIR / 'ASLM_Module.json'
            if json_path.exists():
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    print(f'Module: {data.get('name', 'N/A')}, v{data.get('version', 'N/A')} by {data.get('author', 'N/A')}')
                    print(f'ID: {data.get('id', 'N/A')} | Type: {data.get('type', 'N/A')} | HasPage: {data.get('hasPage', 'N/A')}')
                    if data.get('source').get('type') == "github":
                        print(f'SourceCode: https://github.com/{data.get('source').get('repo')}')
        except:
            print("Error reading config")
        print("------------------------------------------------------")
        print(f'Module Start Time: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        print("------------------------------------------------------")
