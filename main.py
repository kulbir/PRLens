import os
from google import genai
from dotenv import load_dotenv

# Load variables from .env
load_dotenv()

def main():
    # The new SDK automatically looks for the GEMINI_API_KEY env var
    # but we can also pass it explicitly.
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    hardcoded_code = """
    Analyze this code for potential bugs:
    
    def calculate_average(numbers):
        total = sum(numbers)
        return total / len(numbers)
    """

    print("--- Communicating with Gemini ---")
    
    try:
        # Note the change: client.models.generate_content
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite", # You can now use the latest models
            contents=hardcoded_code
        )
        
        print("\nGemini's Response:")
        print(response.text)
        
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()