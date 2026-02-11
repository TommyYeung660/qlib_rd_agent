import os
import sys
from litellm import completion

# Setup environment exactly as in the app
os.environ["VOLCENGINE_API_KEY"] = "0b79bb3c-b1b8-46bf-a104-836c76290427"
os.environ["VOLCENGINE_BASE_URL"] = "https://ark.cn-beijing.volces.com/api/coding/v3"

# Check Proxy Vars
print("--- Environment Check ---")
print(f"HTTP_PROXY: {os.environ.get('HTTP_PROXY')}")
print(f"HTTPS_PROXY: {os.environ.get('HTTPS_PROXY')}")
print(f"http_proxy: {os.environ.get('http_proxy')}")
print(f"https_proxy: {os.environ.get('https_proxy')}")
print("-------------------------")

print("Attempting connection via LiteLLM...")

try:
    # Mimic the curl request exactly
    response = completion(
        model="openai/glm-4.7",  # This uses the openai provider logic with model name "glm-4.7"
        api_key=os.environ["VOLCENGINE_API_KEY"],
        base_url=os.environ["VOLCENGINE_BASE_URL"],
        messages=[{"role": "user", "content": "Hello"}],
        verbose=True,  # Print debug info
    )
    print("\n✅ Success!")
    print(response)
except Exception as e:
    print("\n❌ Failed!")
    print(e)
