import os

# This will try to fetch WWO_KEY from the environment
# if not possible, it will use whatever the user has entered as statickey below
wwo_key = os.getenv('WWO_KEY', "statickey")
