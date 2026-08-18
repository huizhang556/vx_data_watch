from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import DailyAccountMetric, DailyVideoMetric, Video

METRIC_FIELDS = ("plays", "recommendations", "likes", "comments", "shares", "follows", "favorites")


def metric_to_dict(row: DailyAccountMetric) -> dict[str, Any]:
    return {
        "date": row.metric_date.isoformat(),
        **{field: getattr(row, field) for field in METRIC_FIELDS},
    }


def date_summary(db: Session, account_id: int, metric_date: date) -> dict[str, Any]:
    metric = db.scalar(
        select(DailyAccountMetric).where(
            DailyAccountMetric.account_id == account_id,
            DailyAccountMetric.metric_date == metric_date,
        )
    )
    if not metric:
        return {
            "date": metric_date.isoformat(),
            "metric": None,
            "videos": [],
            "reconciliation": None,
        }
    rows = db.execute(
        select(DailyVideoMetric, Video)
        .join(Video, Video.id == DailyVideoMetric.video_id)
        .where(Video.account_id == account_id, DailyVideoMetric.metric_date == metric_date)
        .order_by(DailyVideoMetric.plays.desc())
    ).all()
    video_total = sum(item.plays for item, _video in rows)
    difference = metric.plays - video_total
    coverage = (
        (video_total / metric.plays * 100)
        if metric.plays
        else (100.0 if video_total == 0 else None)
    )
    videos = []
    cumulative_share = 0.0
    for item, video in rows:
        share = item.plays / metric.plays * 100 if metric.plays else 0.0
        cumulative_share += share
        videos.append(
            {
                "id": video.id,
                "title": video.title,
                "published_at": video.published_at,
                "plays": item.plays,
                "share": round(share, 2),
                "cumulative_share": round(cumulative_share, 2),
                "likes": item.likes,
                "comments": item.comments,
                "shares": item.shares,
            }
        )
    return {
        "date": metric_date.isoformat(),
        "metric": metric_to_dict(metric),
        "videos": videos,
        "reconciliation": {
            "account_total": metric.plays,
            "video_total": video_total,
            "difference": difference,
            "coverage": round(coverage, 2) if coverage is not None else None,
            "status": "complete"
            if coverage is not None and abs(difference) <= metric.plays * 0.01
            else "warning",
        },
    }


def range_summary(db: Session, account_id: int, start_date: date, end_date: date) -> dict[str, Any]:
    metrics = db.scalars(
        select(DailyAccountMetric)
        .where(
            DailyAccountMetric.account_id == account_id,
            DailyAccountMetric.metric_date.between(start_date, end_date),
        )
        .order_by(DailyAccountMetric.metric_date)
    ).all()
    trend = [metric_to_dict(row) for row in metrics]
    values = {
        field: [getattr(row, field) for row in metrics if getattr(row, field) is not None]
        for field in METRIC_FIELDS
    }
    totals = {field: sum(field_values) if field_values else None for field, field_values in values.items()}
    averages = {
        field: round(sum(values[field]) / len(values[field]), 2) if values[field] else None
        for field in METRIC_FIELDS
    }
    period_days = (end_date - start_date).days + 1
    previous_end = start_date - timedelta(days=1)
    previous_start = previous_end - timedelta(days=period_days - 1)
    previous_metrics = db.scalars(
        select(DailyAccountMetric)
        .where(
            DailyAccountMetric.account_id == account_id,
            DailyAccountMetric.metric_date.between(previous_start, previous_end),
        )
        .order_by(DailyAccountMetric.metric_date)
    ).all()
    previous_values = {
        field: [getattr(row, field) for row in previous_metrics if getattr(row, field) is not None]
        for field in METRIC_FIELDS
    }
    previous_totals = {
        field: sum(field_values) if field_values else None
        for field, field_values in previous_values.items()
    }
    return {
        "account_id": account_id,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "days_with_data": len(metrics),
        "trend": trend,
        "totals": totals,
        "averages": averages,
        "previous_start_date": previous_start.isoformat(),
        "previous_end_date": previous_end.isoformat(),
        "previous_trend": [metric_to_dict(row) for row in previous_metrics],
        "previous_totals": previous_totals,
    }


def range_has_complete_data(snapshot: dict[str, Any]) -> bool:
    """Return whether every requested calendar day has an account metric row."""
    requested_days = (
        date.fromisoformat(snapshot["end_date"]) - date.fromisoformat(snapshot["start_date"])
    ).days + 1
    return snapshot["days_with_data"] >= requested_days


def range_video_summary(
    db: Session, account_id: int, start_date: date, end_date: date
) -> dict[str, Any]:
    rows = db.execute(
        select(
            Video,
            func.sum(DailyVideoMetric.plays).label("plays"),
            func.sum(DailyVideoMetric.likes).label("likes"),
            func.sum(DailyVideoMetric.comments).label("comments"),
            func.sum(DailyVideoMetric.shares).label("shares"),
        )
        .join(DailyVideoMetric, DailyVideoMetric.video_id == Video.id)
        .where(
            Video.account_id == account_id,
            DailyVideoMetric.metric_date.between(start_date, end_date),
        )
        .group_by(Video.id)
        .order_by(func.sum(DailyVideoMetric.plays).desc())
    ).all()
    account_total = db.scalar(
        select(func.sum(DailyAccountMetric.plays)).where(
            DailyAccountMetric.account_id == account_id,
            DailyAccountMetric.metric_date.between(start_date, end_date),
        )
    ) or 0
    days_with_data = db.scalar(
        select(func.count(DailyAccountMetric.id)).where(
            DailyAccountMetric.account_id == account_id,
            DailyAccountMetric.metric_date.between(start_date, end_date),
        )
    ) or 0
    video_total = sum(int(row.plays or 0) for row in rows)
    cumulative_share = 0.0
    videos = []
    for row in rows:
        share = (int(row.plays or 0) / account_total * 100) if account_total else 0.0
        cumulative_share += share
        videos.append(
            {
                "id": row.Video.id,
                "title": row.Video.title,
                "published_at": row.Video.published_at,
                "plays": int(row.plays or 0),
                "share": round(share, 2),
                "cumulative_share": round(cumulative_share, 2),
                "likes": int(row.likes) if row.likes is not None else None,
                "comments": int(row.comments) if row.comments is not None else None,
                "shares": int(row.shares) if row.shares is not None else None,
            }
        )
    difference = account_total - video_total
    coverage = video_total / account_total * 100 if account_total else None
    return {
        "account_id": account_id,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "days_with_data": int(days_with_data),
        "videos": videos,
        "reconciliation": {
            "account_total": account_total,
            "video_total": video_total,
            "difference": difference,
            "coverage": round(coverage, 2) if coverage is not None else None,
            "status": "complete"
            if coverage is not None and abs(difference) <= account_total * 0.01
            else "warning",
        },
    }
