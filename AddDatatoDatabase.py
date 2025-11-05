import firebase_admin
from firebase_admin import credentials
from firebase_admin import db

cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred, {
    'databaseURL': "https://face-recognition-attenda-a3277-default-rtdb.firebaseio.com/"
})

ref = db.reference('Students')

data = {
    "011":
        {
            "name": "Murtaza Hassan",
            "major": "Robotics",                            
            "starting_year": 2017,
            "total_attendance": 7,
            "standing": "G",
            "year": 4,
            "last_attendance_time": "2022-12-11 00:54:34"
        },
    "012":
        {
            "name": "Emly Blunt",
            "major": "Economics",
            "starting_year": 2021,
            "total_attendance": 12,
            "standing": "B",
            "year": 1,
            "last_attendance_time": "2022-12-11 00:54:34"
        },
    "013":
        {
            "name": "Elon Musk",
            "major": "Physics",
            "starting_year": 2020,
            "total_attendance": 7,
            "standing": "G",
            "year": 2,
            "last_attendance_time": "2022-12-11 00:54:34"
        },
    "014":
        {
            "name": "Priyanshu Sharma",
            "major": "Computer Science",
            "starting_year": 2023,
            "total_attendance": 7,
            "standing": "G",
            "year": 3,
            "last_attendance_time": "2022-12-11 00:54:34"
        },
    "015":
        {
            "name": "Shivanghi",
            "major": "Computer Science",
            "starting_year": 2023,
            "total_attendance": 90,
            "standing": "B",
            "year": 3,
            "last_attendance_time": "2022-12-11 00:54:34"
        },
    "016":
        {
            "name": "Deepti",
            "major": "Computer Science",
            "starting_year": 2023,
            "total_attendance": 1,
            "standing": "G",
            "year": 3,
            "last_attendance_time": "2022-12-11 00:54:34"
        },
    "017":
        {
            "name": "Kaustubh",
            "major": "Computer Science",
            "starting_year": 2023,
            "total_attendance": 78,
            "standing": "G",
            "year": 3,
            "last_attendance_time": "2022-12-11 00:54:34"
        },
    "018":
        {
            "name": "Ansh Sharma",
            "major": "Computer Science",
            "starting_year": 2023,
            "total_attendance": 1,
            "standing": "G",
            "year": 3,
            "last_attendance_time": "2022-12-11 00:54:34"
        },
    "019":
        {
            "name": "Sahil",
            "major": "Computer Science",
            "starting_year": 2023,
            "total_attendance": 1,
            "standing": "G",
            "year": 3,
            "last_attendance_time": "2022-12-11 00:54:34"
        },
}

for key, value in data.items():
    ref.child(key).set(value)