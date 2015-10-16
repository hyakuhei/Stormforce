import requests
import logging
import lxml.html as html

logger = logging.getLogger(__name__)

class Tidesnear():
    def __init__(self):
        self.lookupURL = "https://tidesnear.me/lookup?lat={lat}&lng={lng}&type=None"

    def lookupHTML(self,lat,lng):
        url = self.lookupURL.format(lat=lat,lng=lng)
        response = requests.get(url,allow_redirects=True,verify=False)
        if response.status_code != 200:
            logger.error(response.status_code)
            return None
        else:
            return response.text

    def parseLocation(self,data):
        root = html.document_fromstring(data)
        x = root.xpath("//title")
        loc = " ".join(x[0].text.split(' ')[:-1]) # Drop 'tides from the placename'
        return loc

    def parseTides(self,data):
        root = html.document_fromstring(data)
        timeElements = root.xpath("//time")
        tides = {}
        for timeElement in timeElements:
            tide = {}
            touples = timeElement.items()
            for x in touples:
                if x[0] == 'datetime':
                    tide['datetime'] = x[1]
                    tide['localtime'] = timeElement.text.strip()
                    tide['simpletime'] = self._simpleTime(tide['localtime'])
                    tide['date'] = x[1].split("T")[0]

            for row in timeElement.getparent().getparent().getchildren():
                if ('class', 'type') in row.items():
                    tide['type'] = row.text.strip()

                if ('itemprop', 'description') in row.items():
                    tide['height'] = row.text.strip().split(" ")[0]
                    tide['heightPretty'] = "{}m".format(tide['height'])

            #Above has parsed Tides, Sunrise, Sunset, MoonRise and Moonset
            #lets filter our everything but tides for now
            if "tide" not in tide['type']:
                continue #Jump us to the next timeElement
            else:
                tide['type'] = tide['type'].split(" ")[0]
                #Tide information will be ordered by date
                date = tide['date']
                if date not in tides:
                    tides[date] = []

                tides[date].append(tide)

        return tides


    """
    Removes the AM/PM string
    Seperates out the tz info
    Makes hour 24hour representation
    """
    def _simpleTime(self,timestring):
        time = timestring.split(" ")
        hour = int(time[0].split(":")[0])
        minute = int(time[0].split(":")[1])
        if time[1] == "PM":
            if hour < 12:
                hour += 12

        return "{hour:02}:{minute:02}".format(
            hour=hour,
            minute=minute
        )

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    lat = 52.4140
    lng = -4.0810

    ts = Tidesnear()
    data = ts.lookupHTML(lat,lng)
    location = ts.parseLocation(data)
    tideset = ts.parseTides(data)

    for date in tideset.keys():
        print date
        for tide in tideset[date]:
            print tide
