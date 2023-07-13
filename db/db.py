from pymongo import MongoClient
client = MongoClient('localhost', 27017)
db = client['fastapi']
collection = db['users']
coderunner = db['submissions']
