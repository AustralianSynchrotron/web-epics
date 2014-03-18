from flask import Flask, request, session, render_template
from flask.ext.socketio import SocketIO, emit, join_room, leave_room
from epics import PV
from epics.ca import CASeverityException
from collections import defaultdict
import time

app = Flask(__name__)
app.config.from_pyfile('app.cfg')
app.jinja_env.trim_blocks = True
app.jinja_env.lstrip_blocks = True

socketio = SocketIO(app)

pv_lookup = {}

def pv_changed(pvname, value, **kws):
    data = {'pv': pvname, 'value': value, 'time': time.time()}
    socketio.emit('update', data, room=pvname)

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('add monitor')
def add_monitor(data):
    pvname = data['pv']

    monitors = session.get('monitors', defaultdict(int))
    monitors[pvname] += 1
    session['monitors'] = monitors
    session.modified = True

    if monitors[pvname] > 1:
        # Client was already monitoring this PV so no need to create a
        # monitor or join room.
        return

    if pvname in pv_lookup:
        # A monitor has already been set up for this PV so we can just
        # join the room.
        join_room(pvname)
        return

    try:
        pv_lookup[pvname] = PV(pvname, callback=pv_changed)
    except CASeverityException:
        session['monitors'][pvname] -= 1
    else:
        join_room(pvname)

@socketio.on('remove monitor')
def remove_monitor(data):
    pvname = data['pv']

    monitors = session.get('monitors', defaultdict(int))
    monitors[pvname] = max(monitors[pvname] - 1, 0)
    session['monitors'] = monitors
    session.modified = True

    if monitors[pvname] > 0:
        # Client still has other monitors set up for this PV.
        return

    leave_room(pvname)
    try:
        remaining_monitors = len(socketio.rooms[''][pvname])
    except KeyError:
        remaining_monitors = 0 
    if remaining_monitors == 0 and pvname in pv_lookup:
        pv_lookup[pvname].disconnect()
        del pv_lookup[pvname]

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=80)
