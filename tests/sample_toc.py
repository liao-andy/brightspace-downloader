"""A representative Brightspace content TOC exercising the tricky cases."""

# File payloads keyed by topic id: (content bytes). Used by the mock server.
FILE_BYTES = {
    4775880: b"%PDF-1.4 lecture 1 intro\n" + b"A" * 2000,
    4775881: b"reading material html body" + b"B" * 500,
    4775882: b"%PDF slides 1.2 " + b"C" * 1500,
    4775900: b"%PDF requirements engineering " + b"D" * 3000,
    4775901: b"%PDF domain modeling " + b"E" * 1200,
    5555001: b"week1 copy one",      # duplicate original filename -> must be de-duplicated
    5555002: b"week1 copy two different length",
    6000001: b"zip bytes here" + b"Z" * 800,
    7000001: b"flaky file contents" + b"F" * 1000,   # used for retry test
    7000002: b"incomplete file contents" + b"G" * 1000,  # used for wrong-length test
}

SAMPLE_TOC = {
    "Modules": [
        {
            "ModuleId": 4775781,
            "Title": "Course Information",
            "SortOrder": -109588,
            "Topics": [
                {  # a web link - must be skipped
                    "TopicId": 5166489,
                    "Title": "Mandatory Attendance Checklist",
                    "TypeIdentifier": "Link",
                    "ActivityType": 10,
                    "Url": "https://example.com/checklist",
                    "SortOrder": 1,
                },
            ],
            "Modules": [],
        },
        {
            "ModuleId": 4799832,
            "Title": "Software Engineering Methods (SEM)",
            "SortOrder": -100000,
            "Topics": [],
            "Modules": [
                {
                    "ModuleId": 4775831,
                    "Title": "Week 1",
                    "SortOrder": 10,
                    "Topics": [
                        {
                            "TopicId": 4775880,
                            "Title": "Lecture 1.1 - Introduction and Course Organisation",
                            "TypeIdentifier": "File",
                            "ActivityType": 1,
                            "Url": "/content/enforced/844457-CSE2115+2026+1/Lecture 1 - Introduction.pdf",
                            "SortOrder": 2,
                        },
                        {
                            "TopicId": 4775881,
                            "Title": "Reading Material",
                            "TypeIdentifier": "File",
                            "ActivityType": 1,
                            "Url": "/content/enforced/844457-CSE2115+2026+1/Reading Material - Copy.html",
                            "SortOrder": 1,  # lower sort order -> should come first
                        },
                        {
                            "TopicId": 4775882,
                            "Title": "Lecture 1.2 - Practicing Agility",
                            "TypeIdentifier": "File",
                            "ActivityType": 1,
                            "Url": "/content/enforced/844457-CSE2115+2026+1/Slides: Agility?.pdf",
                            "SortOrder": 3,
                        },
                        {  # a content-service video - must be skipped
                            "TopicId": 5189342,
                            "Title": "Final presentation recording",
                            "TypeIdentifier": "ContentService",
                            "ActivityType": 1,
                            "Url": "d2l:brightspace:content:eu-west-1:abc:video:xyz/latest",
                            "SortOrder": 4,
                        },
                        {  # broken file (no usable url) - must be skipped
                            "TopicId": 4643639,
                            "Title": "Broken topic",
                            "TypeIdentifier": "File",
                            "ActivityType": 1,
                            "Url": None,
                            "IsBroken": True,
                            "SortOrder": 5,
                        },
                    ],
                    "Modules": [
                        {
                            "ModuleId": 4775900,
                            "Title": "Assignment 1 - Requirements",
                            "SortOrder": 20,
                            "Topics": [
                                {
                                    "TopicId": 4775900,
                                    "Title": "Assignment 1 (REQUIRES ATTENDANCE)",
                                    "TypeIdentifier": "File",
                                    "ActivityType": 1,
                                    "Url": "/content/enforced/844457-CSE2115+2026+1/SEM_Assignment_1.pdf",
                                    "SortOrder": 1,
                                },
                            ],
                            "Modules": [],
                        },
                    ],
                },
                {
                    "ModuleId": 4775832,
                    "Title": "Week 2",
                    "SortOrder": 11,
                    "Topics": [
                        {
                            "TopicId": 4775901,
                            "Title": "Lecture 2.1",
                            "TypeIdentifier": "File",
                            "ActivityType": 1,
                            "Url": "/content/enforced/844457-CSE2115+2026+1/Lecture 2.pdf",
                            "SortOrder": 1,
                        },
                        {  # same original filename as the next one -> de-duplicate
                            "TopicId": 5555001,
                            "Title": "Notes copy A",
                            "TypeIdentifier": "File",
                            "ActivityType": 1,
                            "Url": "/content/enforced/844457-CSE2115+2026+1/notes.pdf",
                            "SortOrder": 2,
                        },
                        {
                            "TopicId": 5555002,
                            "Title": "Notes copy B",
                            "TypeIdentifier": "File",
                            "ActivityType": 1,
                            "Url": "/content/enforced/844457-CSE2115+2026+1/notes.pdf",
                            "SortOrder": 3,
                        },
                    ],
                    "Modules": [],
                },
            ],
        },
        {
            "ModuleId": 9999999,
            "Title": "Empty Module",  # no downloadable content -> should not appear
            "SortOrder": -90000,
            "Topics": [
                {"TopicId": 1, "Title": "a link", "TypeIdentifier": "Link", "ActivityType": 2,
                 "Url": "/d2l/le/x", "SortOrder": 1},
            ],
            "Modules": [],
        },
    ],
    "Topics": [],
}

# A second, tiny course used for simpler assertions.
SIMPLE_TOC = {
    "Modules": [
        {
            "ModuleId": 1, "Title": "Week 1", "SortOrder": 1, "Modules": [],
            "Topics": [
                {"TopicId": 6000001, "Title": "Archive", "TypeIdentifier": "File", "ActivityType": 1,
                 "Url": "/content/enforced/1/code.zip", "SortOrder": 1},
            ],
        },
    ],
    "Topics": [],
}
