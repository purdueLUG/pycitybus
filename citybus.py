# a library for interacting with the API of
# CityBus of Lafayette, Indiana, USA

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, List, Optional
import re
import requests

autoupdate_interval = timedelta(minutes=10)
api_url = "https://bus.gocitybus.com"


def colorblocks(hex: str) -> str:
    [r, g, b] = [int(hex[n : n + 2], 16) for n in [1, 3, 5]]
    return f"\x1b[48;2;{r};{g};{b}m    \x1b[0m"


@dataclass
class RouteSegment:
    uuid: str
    is_active: bool
    destination: str
    direction_key: str

    @classmethod
    def from_json(cls, json):
        return cls(
            uuid=json["key"],
            is_active=json["isDisplay"],
            destination=json["destination"],
            direction_key=json["direction"]["key"],
        )


@dataclass
class Route:
    uuid: str
    name: str
    short_name: str
    segments: List[RouteSegment]
    color: str

    @classmethod
    def from_json(cls, json):
        return cls(
            uuid=json["key"],
            name=json["name"],
            short_name=json["shortName"],
            segments=[RouteSegment.from_json(s) for s in json["patternList"]],
            color=json["patternList"][0]["lineColor"],
        )


@dataclass
class ETA:
    route: Route
    departing: datetime

    def __str__(self):
        time = self.departing.strftime("%H:%M")
        color = colorblocks(self.route.color)
        return f"{time} {color}{self.route.short_name: >6} {self.route.name}"


@dataclass
class BusStop:
    id: str
    name: str
    lat: float
    lon: float

    @classmethod
    def from_json(cls, json):
        return cls(
            id=json["stopCode"],
            name=re.sub(r": BUS\w+$", "", json["stopName"]),
            lat=json["latitude"],
            lon=json["longitude"],
        )

    def get_etas(self, cb) -> List[ETA]:
        """Retrieve live ETAs for arriving busses"""

        headers = {"Accept-Language": "en-US,en", "Content-Type": "application/json"}
        data = {"stopCode": self.id}
        j = requests.post(
            api_url + "/Schedule/GetStopEstimates", headers=headers, json=data
        ).json()

        result = []
        for route in j["routeStopSchedules"]:
            for time in route["stopTimes"]:
                if time["isRealtime"]:
                    eta = ETA(
                        cb.get_route(short_name=route["routeNumber"]),
                        datetime.fromisoformat(time["estimatedDepartTime"]),
                    )
                    result.append(eta)

        return sorted(result, key=lambda e: e.departing)

    def __str__(self):
        return f"{self.id: <10} {self.name}"


class CityBus:
    def __init__(self):
        self.update()

    def update(self):
        self.update_stops()
        self.update_routes()
        self.last_updated = datetime.now()

    def update_stops(self):
        """Update list of bus stops"""

        j = requests.get(api_url + "/Home/GetAllBusStops").json()
        self.stops = [BusStop.from_json(stop) for stop in j]

    def update_routes(self):
        """Update running bus routes"""

        headers = {"Accept-Language": "en-US,en", "Content-Length": "0"}
        j = requests.post(api_url + "/RouteMap/GetBaseData/", headers=headers).json()
        self.routes = [Route.from_json(route) for route in j["routes"]]

    def get_etas(self, stop_id: str) -> Optional[List[ETA]]:
        stop = self.get_stop(stop_id)
        return stop.get_etas(self) if stop else None

    def get_stop(self, stop_id: str) -> Optional[BusStop]:
        """Get a specific bus stop"""

        results = [s for s in self.stops if s.id == stop_id]
        if len(results) == 0:
            return None
        else:
            return results[0]

    def search_stops(self, search: str) -> Iterable[BusStop]:
        """Find bus stops matching a string"""

        p = re.compile(search, re.IGNORECASE)
        return filter(lambda s: p.search(s.name), self.stops)

    def get_route(self, **kwargs) -> Optional[BusStop]:
        """Get a specific bus route, either by uuid or short name"""

        if "short_name" in kwargs:
            results = [r for r in self.routes if r.short_name == kwargs["short_name"]]
            if len(results) != 0:
                return results[0]
        elif "uuid" in kwargs:
            results = [r for r in self.routes if r.uuid == kwargs["uuid"]]
            if len(results) != 0:
                return results[0]

        return None

    def search_routes(self, search: str) -> Iterable[Route]:
        """Find bus routes matching a string"""

        p = re.compile(search, re.IGNORECASE)
        return filter(lambda r: p.search(r.name) or p.search(r.short_name), self.routes)
