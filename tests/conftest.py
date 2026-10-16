from elevator_sim.models import Passenger, Request


def passenger(source: int, dest: int, time: int = 0, id: str = "p1") -> Passenger:
    return Passenger(Request(time=time, id=id, source=source, dest=dest))
