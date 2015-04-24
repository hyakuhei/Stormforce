import json
import logging

from flask import Flask
from flask import request
from flask import jsonify
from flask import abort

from WeatherScraper import WeatherScraper
from config import wwo_key

app = Flask(__name__)
logger = logging.getLogger(__name__)

wave_apikey = "jTfvS9EDcCVJ"

ws = None

class InvalidAPIUsage(Exception):
    status_code = 400

    def __init__(self, message, status_code=None, payload=None):
        Exception.__init__(self)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        self.payload = payload

    def to_dict(self):
        rv = dict(self.payload or ())
        rv['message'] = self.message
        return rv

@app.errorhandler(InvalidAPIUsage)
def handle_invalid_usage(error):
    response = jsonify(error.to_dict())
    response.status_code = error.status_code
    return response

@app.route("/")
def ohhai():
    logger.debug("Received connection for unknown route")
    return "ohhai!"

@app.route("/conditions")
def conditions():   
    logger.debug("Starting Condition Search")
    if 'key' not in request.args:
        logger.debug("API key missing from {}".format(request.args))
        raise InvalidAPIUsage('API Key Missing', status_code=500)
    
    if 'lat' not in request.args or 'lon' not in request.args:
        logger.debug("Call is missing lat or long {}".format(request.args))
        raise InvalidAPIUsage('lat/lon Missing', status_code=500)
    
    localConditions = ws.getConditions(request.args['lat'],request.args['lon'])
    
    try:
        logger.debug("Got conditions {}".format(json.dumps(localConditions,sort_keys=True,indent=4,separators=(',',': '))))
    except:
        logger.debug("Unable to identify weather for location {},{}".format(request.args['lat'],request.args['lon']))
        abort(500)
        
    return json.dumps(localConditions,encoding='ascii')

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    ws = WeatherScraper(wwo_key)
    app.run(host='0.0.0.0', debug=False)
    