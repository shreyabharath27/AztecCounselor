"""
Standalone test — confirms your AWS credentials, IAM permissions, and
Nova Lite model access all actually work before touching the real
transcript endpoint.

Run:
    python scripts/test_bedrock.py
"""

import os
import boto3
from dotenv import load_dotenv

load_dotenv()

AWS_REGION = os.getenv("AWS_REGION")

client = boto3.client("bedrock-runtime", region_name=AWS_REGION)

response = client.converse(
    modelId="amazon.nova-lite-v1:0",
    messages=[
        {
            "role": "user",
            "content": [{"text": "Say hello and confirm you're Nova Lite, in one sentence."}],
        }
    ],
)

output_text = response["output"]["message"]["content"][0]["text"]
print("Bedrock responded successfully:\n")
print(output_text)