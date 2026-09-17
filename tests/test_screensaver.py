import threading
from unittest.mock import Mock

from PIL import Image

from soomfon_control.config import App, Button, Config, ScreensaverConfig
from soomfon_control.controller import Controller
from soomfon_control.screensaver import Screensaver


def make_saver(tmp_path):
    paths = []
    for i in range(8):
        path = tmp_path / f"{i}.png"
        Image.new("RGB", (64, 64), (i * 30, 10, 20)).save(path)
        paths.append(path)
    now = [0.0]
    deck = Mock()
    icons = [Image.new("RGB", (60, 60), "white") for _ in range(6)]
    saver = Screensaver(deck, ScreensaverConfig(tuple(paths)), icons, clock=lambda: now[0])
    return saver, deck, now, icons


def test_idle_timeout_animation_and_wake(tmp_path):
    saver, deck, now, icons = make_saver(tmp_path)
    saver._delay = lambda: 2
    now[0] = 9.99
    saver.tick()
    deck.set_key_image.assert_not_called()
    now[0] = 10
    saver.tick()
    assert saver.active
    assert deck.set_key_image.call_count == 6
    assert len({id(c.args[1]) for c in deck.set_key_image.call_args_list}) == 6
    now[0] = 11
    saver.tick()
    assert deck.set_key_image.call_count == 6
    now[0] = 12
    saver.tick()
    assert deck.set_key_image.call_count == 7
    assert saver.activity()
    saver.tick()
    assert not saver.active
    assert [c.args[1] for c in deck.set_key_image.call_args_list[-6:]] == icons
    now[0] = 21.99
    saver.tick()
    assert not saver.active
    now[0] = 22
    saver.tick()
    assert saver.active
    saver.close()
    assert [c.args[1] for c in deck.set_key_image.call_args_list[-6:]] == icons


def test_input_resets_idle_timer(tmp_path):
    saver, deck, now, _ = make_saver(tmp_path)
    now[0] = 9
    assert not saver.activity(wake=False)
    now[0] = 10
    saver.tick()
    deck.set_key_image.assert_not_called()
    now[0] = 19
    saver.tick()
    assert saver.active
    saver.close()


def test_wake_cancels_inflight_frame_and_restores_all_icons(tmp_path):
    saver, deck, now, icons = make_saver(tmp_path)
    entered, release = threading.Event(), threading.Event()
    def upload(key, image):
        if not entered.is_set():
            entered.set()
            assert release.wait(2)
    deck.set_key_image.side_effect = upload
    now[0] = 10
    worker = threading.Thread(target=saver.tick)
    worker.start()
    try:
        assert entered.wait(2)
        assert saver.activity()  # Must not block on the USB write.
    finally:
        release.set()
        worker.join(2)
    assert not worker.is_alive()
    assert deck.set_key_image.call_count == 1
    saver.tick()
    assert [c.args[1] for c in deck.set_key_image.call_args_list[-6:]] == icons
    saver.close()


def test_first_app_press_only_wakes_and_next_press_acts():
    actions = Mock()
    app = App(("example.exe",), "example.exe")
    controller = Controller(Config(70, 1, 1, {0: Button("App", app=app)}), actions)
    saver = Mock()
    saver.activity.side_effect = [True, False, False]
    controller._screensaver = saver
    try:
        controller.on_key(0, True)
        actions.activate.assert_not_called()
        controller.on_key(0, False)
        actions.activate.assert_not_called()
        controller.on_key(0, True)
    finally:
        controller.close()
    actions.activate.assert_called_once_with(app)


def test_knob_press_only_wakes_and_volume_turn_still_works():
    actions = Mock()
    controller = Controller(Config(70, 1, 1, {}), actions)
    controller._screensaver = Mock()
    try:
        controller.on_key(10, True)
        actions.play_pause.assert_not_called()
        controller.on_encoder(1, -1)
        actions.volume.assert_called_once_with(-1)
    finally:
        controller.close()


def test_independent_deadlines_and_new_random_delay_each_update(tmp_path):
    saver, deck, now, _ = make_saver(tmp_path)
    saver._delay = Mock(side_effect=[1, 1.3, 1.6, 1.9, 2.2, 2.5, 2.8, 1.1])
    now[0] = 10
    saver.tick()
    assert saver._next_frame == [11, 11.3, 11.6, 11.9, 12.2, 12.5]
    first_face = saver._current_faces[0]
    deck.reset_mock()
    now[0] = 11
    saver.tick()
    assert [c.args[0] for c in deck.set_key_image.call_args_list] == [0]
    assert saver._current_faces[0] != first_face
    assert saver._next_frame[0] == 13.8
    assert saver._next_frame[1:] == [21.3, 21.6, 21.9, 22.2, 22.5]
    assert len(set(saver._current_faces)) == 6
    deck.reset_mock()
    now[0] = 11.3
    saver.tick()
    assert [c.args[0] for c in deck.set_key_image.call_args_list] == [0]
    assert len(set(saver._current_faces)) == 6


def test_random_delay_range(tmp_path):
    saver, _, _, _ = make_saver(tmp_path)
    delays = [saver._delay() for _ in range(100)]
    assert all(30 <= delay <= 90 for delay in delays)
    assert len(set(delays)) > 1


def test_page_icons_replace_screensaver_and_are_restored_on_next_wake(tmp_path):
    saver, deck, now, _ = make_saver(tmp_path)
    now[0] = 10
    saver.tick()
    new_icons = [Image.new("RGB", (60, 60), "blue") for _ in range(6)]
    saver.set_icons(new_icons)
    deck.reset_mock()
    saver.tick()
    assert not saver.active
    assert [call.args[1] for call in deck.set_key_image.call_args_list] == new_icons
    now[0] = 20
    saver.tick()
    assert saver.active
    saver.activity()
    deck.reset_mock()
    saver.tick()
    assert [call.args[1] for call in deck.set_key_image.call_args_list] == new_icons


def test_overdue_faces_are_spaced_out_and_fades_do_not_extend_cooldown(tmp_path):
    saver, deck, now, _ = make_saver(tmp_path)
    saver._delay = lambda: 60
    now[0] = 10
    saver.tick()
    saver._next_frame = [30, 29, 31, 32, 33, 100]
    original = saver._current_faces.copy()
    now[0] = 40
    saver.tick()
    assert [i for i in range(6) if saver._current_faces[i] != original[i]] == [1]
    assert saver._next_frame == [50, 100, 50, 50, 50, 110]
    assert saver._next_change == 50
    while saver._fade_frames[1]:
        now[0] = saver._next_fade[1]
        saver.tick()
    assert saver._next_change == 50
    assert saver._next_frame == [50, 100, 50, 50, 50, 110]
    after_first = saver._current_faces.copy()
    now[0] = 49.99
    saver.tick()
    assert saver._current_faces == after_first
    now[0] = 50
    saver.tick()
    assert [i for i in range(6) if saver._current_faces[i] != after_first[i]] == [0]
    assert saver._next_frame == [110, 110, 60, 60, 60, 120]


def test_changed_face_fades_out_then_in_without_touching_other_buttons(tmp_path):
    saver, deck, now, _ = make_saver(tmp_path)
    saver._delay = lambda: 6
    now[0] = 10
    saver.tick()
    old_face = saver.faces[saver._current_faces[0]]
    saver._next_frame = [13] + [30] * 5
    deck.reset_mock()
    now[0] = 13
    saver.tick()
    face = saver.faces[saver._current_faces[0]]
    while saver._fade_frames[0]:
        now[0] = saver._next_fade[0]
        saver.tick()
    calls = deck.set_key_image.call_args_list
    assert len(calls) == 12
    assert all(call.args[0] == 0 for call in calls)
    pixels = [sum(call.args[1].getpixel((30, 30))) for call in calls]
    assert sum(old_face.getpixel((30, 30))) > pixels[0]
    assert pixels[:6] == sorted(pixels[:6], reverse=True)
    assert pixels[5] == 0
    assert pixels[6:] == sorted(pixels[6:])
    assert calls[-1].args[1].tobytes() == face.tobytes()
    assert not saver._fade_frames[0]


def test_waking_mid_fade_cancels_transition_and_restores_icons(tmp_path):
    saver, deck, now, icons = make_saver(tmp_path)
    saver._delay = lambda: 3
    now[0] = 10
    saver.tick()
    now[0] = 13
    saver.tick()
    now[0] = 13.2
    saver.tick()
    assert saver._fade_frames[0]
    assert saver.activity()
    deck.reset_mock()
    saver.tick()
    assert [call.args[1] for call in deck.set_key_image.call_args_list] == icons
    now[0] = 14
    saver.tick()
    assert deck.set_key_image.call_count == 6
    assert not any(saver._fade_frames)
