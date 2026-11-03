import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    api_key=os.getenv("keyone"),
    base_url="https://inference.generativeai.us-chicago-1.oci.oraclecloud.com/20231130/actions/v1",
    default_headers={
        # This header is often the missing link for 401 errors
        "opc-compartment-id": os.getenv("OCI_COMPARTMENT_ID")
    }
)

try:
    print("Sending request...")
    response = client.chat.completions.create(
        model="meta.llama-3.1-70b-instruct", 
        messages=[{"role": "user", "content": "Hello"}]
    )
    print("Success!")
except Exception as e:
    print(f"Error: {e}")