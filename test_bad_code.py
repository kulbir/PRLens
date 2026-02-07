# BAD CODE - For testing PRLens
# Contains: bugs, security issues, PEP8 violations, performance issues

import os
import pickle

Password = "admin123"  # Hardcoded password (security issue + wrong naming)

def divide(a,b):  # Missing spaces (PEP8), missing docstring
    return a/b  # Division by zero bug

def getUserData(userId):  # Wrong naming convention (should be snake_case)
    query = "SELECT * FROM users WHERE id = " + userId  # SQL Injection!
    return query

def processItems(items):
    result = []
    for i in range(len(items)):  # Should use enumerate or direct iteration
        result.append(items[i] * 2)
    return result

def load_user_data(filename):
    with open(filename, 'rb') as f:
        return pickle.load(f)  # Insecure deserialization!

class user:  # Class name should be PascalCase
    def __init__(self,name,age):  # Missing spaces after commas
        self.name=name  # Missing spaces around =
        self.age=age

def calculate_average(numbers):
    total = sum(numbers)
    return total / len(numbers)  # ZeroDivisionError if empty

def fetchAPI():  # Wrong naming, no error handling
    import requests  # Import should be at top
    response = requests.get("http://api.example.com")  # HTTP not HTTPS
    return response.json()

def main():
    print(divide(10, 0))  # Will crash
    print(getUserData("1; DROP TABLE users;"))  # SQL injection example
    data = calculate_average([])  # Will crash

if __name__ == "__main__":
    main()

