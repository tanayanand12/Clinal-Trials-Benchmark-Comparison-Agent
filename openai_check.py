# deep_debug_openai.py
import os
import sys
import inspect
from dotenv import load_dotenv

# Clear ALL possible proxy-related environment variables
print("=== Clearing Environment Variables ===")
proxy_vars = [
    'HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 
    'ALL_PROXY', 'all_proxy', 'NO_PROXY', 'no_proxy',
    'OPENAI_PROXY', 'OPENAI_PROXIES', 'OPENAI_API_BASE',
    'REQUESTS_CA_BUNDLE', 'CURL_CA_BUNDLE'
]

for var in proxy_vars:
    if var in os.environ:
        print(f"Removing: {var}={os.environ[var]}")
        del os.environ[var]
    else:
        print(f"Not set: {var}")

load_dotenv()

print("\n=== Python Environment Info ===")
print(f"Python version: {sys.version}")
print(f"Python executable: {sys.executable}")

print("\n=== OpenAI Installation Check ===")
try:
    import openai
    print(f"OpenAI version: {openai.__version__}")
    print(f"OpenAI module location: {openai.__file__}")
    
    # Check if openai has any global proxy settings
    if hasattr(openai, 'proxy'):
        print(f"OpenAI global proxy: {openai.proxy}")
    else:
        print("No global proxy attribute found")
        
    # Check if there are any global configurations
    if hasattr(openai, 'api_base'):
        print(f"OpenAI api_base: {openai.api_base}")
    
except Exception as e:
    print(f"Error importing openai: {e}")
    sys.exit(1)

print("\n=== Monkey Patch to Debug Constructor ===")
# Monkey patch the OpenAI constructor to see what's being passed
original_init = openai.OpenAI.__init__

def debug_init(self, *args, **kwargs):
    print(f"OpenAI.__init__ called with:")
    print(f"  args: {args}")
    print(f"  kwargs: {kwargs}")
    
    if 'proxies' in kwargs:
        print("❌ FOUND 'proxies' in kwargs!")
        print("Call stack showing where 'proxies' came from:")
        for i, frame in enumerate(inspect.stack()):
            print(f"  [{i}] {frame.filename}:{frame.lineno} in {frame.function}")
        
        # Remove the problematic argument
        print("Removing 'proxies' argument and continuing...")
        kwargs.pop('proxies', None)
    
    return original_init(self, *args, **kwargs)

openai.OpenAI.__init__ = debug_init

print("\n=== Test Basic OpenAI Client Creation ===")
try:
    # Test with minimal arguments
    print("Attempting: openai.OpenAI()")
    client1 = openai.OpenAI()
    print("✓ Success with no arguments")
except Exception as e:
    print(f"✗ Failed with no arguments: {e}")

try:
    # Test with API key only
    print(f"\nAttempting: openai.OpenAI(api_key='test-key')")
    client2 = openai.OpenAI(api_key="test-key")
    print("✓ Success with API key")
except Exception as e:
    print(f"✗ Failed with API key: {e}")

try:
    # Test with environment variable
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        print(f"\nAttempting: openai.OpenAI(api_key=env_var)")
        client3 = openai.OpenAI(api_key=api_key)
        print("✓ Success with environment API key")
    else:
        print("No OPENAI_API_KEY found in environment")
except Exception as e:
    print(f"✗ Failed with environment API key: {e}")

print("\n=== Check for Other Libraries That Might Interfere ===")
potentially_interfering = [
    'httpx', 'requests', 'urllib3', 'aiohttp', 'httpcore'
]

for lib in potentially_interfering:
    try:
        module = __import__(lib)
        print(f"{lib}: {getattr(module, '__version__', 'unknown version')}")
    except ImportError:
        print(f"{lib}: not installed")

print("\n=== Check OpenAI Client Signature ===")
import inspect
sig = inspect.signature(openai.OpenAI.__init__)
print(f"OpenAI.__init__ signature: {sig}")

print("\n=== Environment Variables After Cleanup ===")
env_vars = {k: v for k, v in os.environ.items() if 'proxy' in k.lower() or 'openai' in k.lower()}
if env_vars:
    print("Remaining proxy/openai related env vars:")
    for k, v in env_vars.items():
        print(f"  {k}={v}")
else:
    print("No proxy/openai related env vars remaining")

print("\n=== Try Manual Client Creation ===")
try:
    # Try creating client with explicit parameters
    kwargs = {
        'api_key': os.getenv('OPENAI_API_KEY', 'test-key')
    }
    
    print(f"Manual creation with kwargs: {kwargs}")
    manual_client = openai.OpenAI(**kwargs)
    print("✓ Manual creation successful")
    
except Exception as e:
    print(f"✗ Manual creation failed: {e}")
    import traceback
    traceback.print_exc()