AutoZoom
========
Designed for Accessibility and MacOS, this program runs in the background and then prompts the user if an upcoming meeting is about to start, providing an option to join the meeting via Zoom.

This project uses the [Google Calendar API for Python](https://developers.google.com/calendar/quickstart/python)

## Setup
1. rename `configs.py.template` to `configs.py` and change the settings in that file to suit your needs.
2. It's recommended to use [supervisord](http://supervisord.org/) to keep the program running in the background.