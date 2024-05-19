import json
from typing import Any
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.middleware import csrf


def get_json_body(request: HttpRequest) -> dict[str, Any]:
    return json.loads(request.body)


def get_csrf_token(request: HttpRequest) -> HttpResponse:
    return JsonResponse(
        {
            "data": csrf.get_token(request)
        }
    )


def test_api(request: HttpRequest):
    body = get_json_body(request)
    num1 = body["num1"]
    num2 = body["num2"]
    return JsonResponse(
        {
            "data": float(num1) + float(num2)
        }
    )
