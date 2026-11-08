from jcan.can_transport import create_bus
from jcan.dtc import decode_dtcs
from jcan.obd2 import Obd2Session
from jcan.readiness import decode_readiness
from jcan.simulator import FAKE_VIN, Simulator


def _make_session(channel):
    bus_sim = create_bus("virtual", channel)
    bus_client = create_bus("virtual", channel)
    sim = Simulator(bus_sim)
    sim.start()
    session = Obd2Session(bus_client, timeout=1.0)
    return sim, session, bus_sim, bus_client


def test_simulator_rpm_pid():
    sim, session, bus_sim, bus_client = _make_session("sim-test-1")
    try:
        data = session.read_pid(0x0C)
        rpm = ((data[0] * 256) + data[1]) / 4
        assert 3000 <= rpm <= 4000
    finally:
        session.close()
        sim.stop()
        bus_sim.shutdown()
        bus_client.shutdown()


def test_simulator_vin():
    sim, session, bus_sim, bus_client = _make_session("sim-test-2")
    try:
        assert session.read_vin() == FAKE_VIN
    finally:
        session.close()
        sim.stop()
        bus_sim.shutdown()
        bus_client.shutdown()


def test_simulator_dtcs_then_clear():
    sim, session, bus_sim, bus_client = _make_session("sim-test-3")
    try:
        codes = decode_dtcs(session.read_dtcs())
        assert codes == ["P0133", "P0301"]

        session.clear_dtcs()

        assert decode_dtcs(session.read_dtcs()) == []
    finally:
        session.close()
        sim.stop()
        bus_sim.shutdown()
        bus_client.shutdown()


def test_simulator_readiness_reflects_dtc_state():
    sim, session, bus_sim, bus_client = _make_session("sim-test-4")
    try:
        before = decode_readiness(session.read_pid(0x01))
        assert before["mil_on"] is True
        assert before["dtc_count"] == 2
        assert {"name": "components", "ready": False} in before["monitors"]

        session.clear_dtcs()

        after = decode_readiness(session.read_pid(0x01))
        assert after["mil_on"] is False
        assert after["dtc_count"] == 0
    finally:
        session.close()
        sim.stop()
        bus_sim.shutdown()
        bus_client.shutdown()
