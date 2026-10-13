"""Unit tests for sctrl.model_db."""

from __future__ import annotations

import pytest
from sctrl.constants import MODELS_DB_DIR
from sctrl.model_db import ModelDatabase, compute_support_tier
from sctrl.models import DMIInfo, SupportTier


def test_model_db_load(model_db: ModelDatabase) -> None:
    profiles = model_db.profiles
    assert len(profiles) >= 1
    phn16 = model_db.find_profile(DMIInfo(product_name="PHN16-72"))
    assert phn16 is not None
    assert "PHN16-72" in phn16.product_names
    assert phn16.primary_driver == "acer-wmi"


def test_compute_support_tier(model_db: ModelDatabase) -> None:
    # 1. Matched profile without physical verification = COMMUNITY
    dmi_comm = DMIInfo(product_name="PHN16-72", board_name="Covini_PH16-72", vendor="Acer", bios_version="V1.06")
    prof = model_db.find_profile(dmi_comm)
    res_comm = compute_support_tier(dmi_comm, prof)
    assert res_comm.tier == SupportTier.COMMUNITY

    # 2. Acer laptop with no profile match = DETECTED
    dmi_detected = DMIInfo(product_name="AN515-58", vendor="Acer", sys_vendor="Acer")
    prof_det = model_db.find_profile(dmi_detected)
    assert prof_det is None
    res_det = compute_support_tier(dmi_detected, prof_det)
    assert res_det.tier == SupportTier.DETECTED

    # 3. Non-Acer laptop = UNSUPPORTED
    dmi_unsupp = DMIInfo(product_name="ThinkPad T14", vendor="Lenovo", sys_vendor="Lenovo")
    prof_unsupp = model_db.find_profile(dmi_unsupp)
    res_unsupp = compute_support_tier(dmi_unsupp, prof_unsupp)
    assert res_unsupp.tier == SupportTier.UNSUPPORTED
