import os
import json
import requests

POSTMAN_API_KEY = os.getenv("POSTMAN_API_KEY")
POSTMAN_COLLECTION_ID = os.getenv("POSTMAN_COLLECTION_ID")

def send_schema_to_postman():
    with open('postman_collection.json', 'r') as f:
        collection = json.load(f)

    headers = {
        "x-api-key": f"{POSTMAN_API_KEY}",
        "Content-Type": "application/json"
    }

    api_url = f'https://api.getpostman.com/collections/{POSTMAN_COLLECTION_ID}'

    res = requests.put(api_url, headers=headers, json={"collection": collection})

    if res.status_code == 200:
        print("OpenAPI schema successfully sent to Postman.")
    else:
        print(f"Failed to send schema to Postman: {res.text}")
    
if __name__ == "__main__":
    send_schema_to_postman()
    