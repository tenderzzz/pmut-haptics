from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest


def test_demo_initial_render_stale_notice_and_rerun():
    app_path = Path(__file__).parents[1]/"src/pmut_haptics/demo.py"
    at = AppTest.from_file(str(app_path), default_timeout=40).run()
    assert not at.exception
    assert len(at.metric) == 4
    at.selectbox[0].select("圆形轨迹").run()
    assert any("参数已改变" in item.value for item in at.info)
    button = next(b for b in at.button if b.label == "运行仿真")
    button.click().run()
    assert not at.exception
    assert at.session_state["result"].config.trajectory.kind == "circle"
