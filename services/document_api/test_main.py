from fastapi.testclient import TestClient

from services.document_api.main import app

client = TestClient(app)


def test_structured_diff_marks_core_change_high():
    response = client.post(
        "/v1/diff/structured",
        json={
            "baseline": [{"code": "DISPUTE", "content": "甲方所在地法院", "core": True}],
            "submitted": [{"code": "DISPUTE", "content": "乙方所在地法院"}],
        },
    )
    assert response.status_code == 200
    result = response.json()
    assert result["risk_level"] == "HIGH"
    assert result["items"][0]["change"] == "MODIFIED"


def test_mask_preview_masks_common_identifiers():
    response = client.post(
        "/v1/mask/preview",
        json={"text": "联系人 13800138000，邮箱 legal@example.com"},
    )
    assert response.status_code == 200
    result = response.json()
    assert "13800138000" not in result["masked_text"]
    assert "legal@example.com" not in result["masked_text"]
    assert result["entity_counts"]["MOBILE"] == 1
