import os, threading, time
from tkinter import *
from tkinter.ttk import *
import datetime
from dateutil.tz import resolve_imaginary, UTC
import pickle
import os.path
import dateutil.parser
import json
import configs
from bs4 import BeautifulSoup
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

EVENTS_CACHE_FILE = configs.EVENTS_CACHE_FILE
SLEEP_TIME_MINUTES = configs.SLEEP_TIME_MINUTES
CALENDAR_ID = configs.GOOGLE_CALENDAR_ID

def check_already_prompted(event_start: str, event_summary: str) -> bool:
    if not os.path.isfile(EVENTS_CACHE_FILE):
        return False
    with open(EVENTS_CACHE_FILE) as json_file:
        events_cache = json.load(json_file)
    if 'events_prompted' not in events_cache:
        return False
    if event_start in events_cache['events_prompted'] and events_cache['events_prompted'][event_start] == event_summary:
        return True
    return False


def remember_already_prompted(event_start: str, event_summary: str):
    if not os.path.isfile(EVENTS_CACHE_FILE):
        events_cache = {}
    else:
        with open(EVENTS_CACHE_FILE) as json_file:
            events_cache = json.load(json_file)
    if 'events_prompted' not in events_cache:
        events_cache['events_prompted'] = {}
    events_cache['events_prompted'][event_start] = event_summary
    with open(EVENTS_CACHE_FILE, 'w') as outfile:
        json.dump(events_cache, outfile)


def walltimedelta(start, end, tz=None) -> datetime.timedelta:
    """
    Time period in wall time. DST offsets are taken into account.
    see https://github.com/dateutil/dateutil/issues/1039#issue-613403091
    """

    if tz is None:
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError('Some datetime is naive and no time zone provided.')
        elif start.tzinfo is not end.tzinfo:
            raise ValueError('Datetimes are on different time zones.')
    else:
        start = start.replace(tzinfo=tz)
        end = end.replace(tzinfo=tz)

    start = resolve_imaginary(start).astimezone(UTC)
    end = resolve_imaginary(end).astimezone(UTC)

    return end - start


def nowtimedelta_minutes(start_datetime: datetime.datetime, current_datetime: datetime.datetime = None) -> float:
    if current_datetime is None:
        current_datetime = dateutil.parser.parse(datetime.datetime.now(start_datetime.tzinfo).isoformat())
    return walltimedelta(current_datetime, start_datetime).total_seconds() / 60


class Application(Frame):
    def __init__(self, master=None, event_desc: str = None, event_url: str = None):
        super().__init__(master)
        self.master = master
        self.event_desc = event_desc
        self.event_url = event_url
        self.pack()
        self.create_widgets()

    def create_widgets(self):
        # background="..." doesn't work on macOS
        # see https://stackoverflow.com/a/9543342/940217
        self.join_img = PhotoImage(file='button_images/join.png')
        self.leave_img = PhotoImage(file='button_images/leave.png')

        self.join_button = Button(self, image=self.join_img, command=self.open_zoom)
        self.join_button.pack(in_=self, side=LEFT, fill=Y)

        self.quit_button = Button(self, image=self.leave_img, command=self.master.destroy)
        self.quit_button.pack(in_=self, side=RIGHT, fill=Y)

    def open_zoom(self):
        try:
            zoom_id = re.search(r"zoom.us/j/(.*$)", self.event_url).group(1)
            zoom_url = f"zoommtg://zoom.us/join?confno={zoom_id}"
            print(f"opening zoom meeting {self.event_desc} at {zoom_url}")
            os.system(f" open \"{zoom_url}\"")
        except Exception as e:
            print(f"Failed to parse zoom meeting ID from url=\"{self.event_url}\"\n{e}")
        self.master.destroy()


def open_prompt(event_desc, event_url):
    # os.system(f"say -v Samantha -r 130 \"Your meeting is ready for {event_desc}\"")
    root = Tk()
    root.geometry("1600x800")
    app = Application(master=root, event_desc=event_desc, event_url=event_url)
    app.pack()
    root.after(func=check_next_meeting, ms=SLEEP_TIME_MINUTES * 60 * 1000)
    root.mainloop()


def parse_event_desc(description: str):
    soup = BeautifulSoup(description, 'html.parser')
    soup.prettify()
    anchor_tags = soup.find_all('a')
    zoom_invite_url = None
    if len(anchor_tags) is not 0:
        zoom_invite_url = anchor_tags[0].get('href')
    return zoom_invite_url


def check_next_meeting():
    print(f'thread {threading.currentThread().getName()} Starting')
    creds = None
    # The file token.pickle stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

    service = build('calendar', 'v3', credentials=creds)

    # Call the Calendar API
    now = datetime.datetime.utcnow().isoformat() + 'Z'  # 'Z' indicates UTC time
    print(f'Getting the upcoming event, from UTC time={now}')
    events_result = service.events().list(calendarId=CALENDAR_ID, timeMin=now,
                                          timeZone="Etc/UTC",
                                          maxResults=2).execute()
    events = events_result.get('items', [])

    if not events:
        print('No upcoming events found.')
    for event in events:
        start = event['start'].get('dateTime', event['start'].get('date'))
        start_date = dateutil.parser.parse(start)

        delta_t_minutes = nowtimedelta_minutes(start_datetime=start_date)
        print(f"The next meeting, \"{event['summary']}\" is {delta_t_minutes:.2f} minutes away")
        if 0 <= delta_t_minutes <= SLEEP_TIME_MINUTES:
            if check_already_prompted(event['start']['dateTime'], event['summary']):
                print('already prompted for this event')
                return False
            else:
                remember_already_prompted(event['start']['dateTime'], event['summary'])
                print(f"{start} ({delta_t_minutes:.2f} away) {event['summary']}")
                if 'description' in event:
                    if event['description'] is not None:
                        open_prompt(event_desc=event['summary'], event_url=parse_event_desc(event['description']))
                        return True


def threadmain():
    while not check_next_meeting():
        time.sleep(SLEEP_TIME_MINUTES*60)


if __name__ == '__main__':
    threadmain()
