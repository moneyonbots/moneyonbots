from django.conf import settings
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver



class MarketSignal(models.Model):
    """Latest (and historical) analysis result for one market. The analysis
    loop upserts one row of history per scan; the dashboard reads the most
    recent row per symbol."""

    DIRECTION_CHOICES = [("Buy", "Buy"), ("Sell", "Sell"), ("Neutral", "Neutral")]
    RISK_CHOICES = [("low", "Low"), ("normal", "Normal"), ("high", "High")]

    symbol = models.CharField(max_length=32, db_index=True)
    market_name = models.CharField(max_length=64)
    market_type = models.CharField(max_length=16)
    timeframe = models.CharField(max_length=8, blank=True, default="1H")
    strategy_mode = models.CharField(max_length=16, blank=True, default="default", 
                                   help_text="Analysis mode used to generate this signal")
    market_regime = models.CharField(max_length=16, blank=True, default="",
                                   help_text="Market regime detected when signal was generated")

    direction = models.CharField(max_length=8, choices=DIRECTION_CHOICES, default="Neutral")
    signal_strength = models.FloatField(default=0)
    setup_quality = models.FloatField(default=0)
    opportunity_score = models.FloatField(default=0)
    entry_type = models.CharField(max_length=32, blank=True, default="")
    risk_level = models.CharField(max_length=8, choices=RISK_CHOICES, default="normal")
    structure = models.CharField(max_length=16, blank=True, default="Neutral")

    price = models.FloatField()
    rsi = models.FloatField(null=True, blank=True)
    atr = models.FloatField(null=True, blank=True)
    stop_loss = models.FloatField(null=True, blank=True)
    take_profit = models.FloatField(null=True, blank=True)
    risk_reward = models.FloatField(null=True, blank=True)
    model_confidence = models.FloatField(null=True, blank=True)
    confirmation_count = models.IntegerField(default=0)
    pattern = models.CharField(max_length=100, blank=True, default="")
    patterns_identified = models.JSONField(default=list, blank=True)
    support_resistance = models.JSONField(default=dict, blank=True)
    technical_notes = models.JSONField(default=list, blank=True)
    
    # News sentiment analysis
    news_sentiment = models.FloatField(null=True, blank=True)
    news_count = models.IntegerField(default=0)
    
    # Trade execution tracking
    status = models.CharField(max_length=16, default="active", choices=[("active", "Active"), ("completed", "Completed")])
    pnl_hit = models.CharField(max_length=8, blank=True, default="", choices=[("tp", "TP"), ("sl", "SL"), ("", "None")])
    actual_pnl = models.FloatField(null=True, blank=True)
    exit_price = models.FloatField(null=True, blank=True)
    current_price = models.FloatField(null=True, blank=True)  # Track current price for active signals
    completed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    htf_advice = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["symbol", "-created_at"])]

    def __str__(self):
        return f"{self.symbol} {self.direction} ({self.signal_strength:.2f}) @ {self.created_at:%H:%M:%S}"

    def as_dict(self):
        return {
            "id": self.pk,
            "symbol": self.symbol,
            "market_name": self.market_name,
            "market_type": self.market_type,
            "timeframe": self.timeframe,
            "direction": self.direction,
            "signal_strength": round(self.signal_strength, 3),
            "setup_quality": round(self.setup_quality, 1),
            "opportunity_score": round(self.opportunity_score, 1),
            "entry_type": self.entry_type,
            "risk_level": self.risk_level,
            "structure": self.structure,
            "price": self.price,
            "current_price": self.current_price,  # Add current price for active signals
            "rsi": round(self.rsi, 1) if self.rsi is not None else None,
            "atr": self.atr,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "risk_reward": self.risk_reward,
            "model_confidence": round(self.model_confidence, 3) if self.model_confidence is not None else None,
            "confirmation_count": self.confirmation_count,
            "pattern": self.pattern,
            "patterns_identified": self.patterns_identified,
            "support_resistance": self.support_resistance,
            "technical_notes": self.technical_notes,
            "news_sentiment": round(self.news_sentiment, 3) if self.news_sentiment is not None else None,
            "news_count": self.news_count,
            "status": self.status,
            "pnl_hit": self.pnl_hit,
            "actual_pnl": self.actual_pnl,
            "exit_price": self.exit_price,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": (self.completed_at or self.created_at).isoformat(),
            "htf_advice": self.htf_advice,
            "strategy_mode": self.strategy_mode,
            "market_regime": self.market_regime,
        }


class UserProfile(models.Model):
    """User profile for trading dashboard preferences, favorite markets tracking,
    and personalized email analysis alerts."""

    DIRECTION_PREFERENCES = [
        ("all", "All Directions"),
        ("Buy", "Buy Signals Only"),
        ("Sell", "Sell Signals Only"),
    ]

    TIMEFRAME_PREFERENCES = [
        ("all", "All Timeframes"),
        ("1H", "1 Hour (1H)"),
        ("4H", "4 Hours (4H)"),
        ("1D", "1 Day (1D)"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile"
    )
    favorites = models.JSONField(
        default=list,
        blank=True,
        help_text="List of market symbols starred by user"
    )
    email_alerts_enabled = models.BooleanField(
        default=True,
        help_text="Whether to dispatch trade signal alerts to user email"
    )
    alert_min_quality = models.IntegerField(
        default=70,
        help_text="Minimum setup quality score (0-100%) to trigger an email alert"
    )
    alert_directions = models.CharField(
        max_length=16,
        choices=DIRECTION_PREFERENCES,
        default="all"
    )
    alert_favorites_only = models.BooleanField(
        default=False,
        help_text="If True, only send alerts for symbols in favorites list"
    )
    alert_timeframe = models.CharField(
        max_length=16,
        choices=TIMEFRAME_PREFERENCES,
        default="all"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"UserProfile({self.user.email or self.user.username})"

    def is_favorite(self, symbol: str) -> bool:
        return symbol in (self.favorites or [])

    def toggle_favorite(self, symbol: str) -> bool:
        favs = list(self.favorites or [])
        if symbol in favs:
            favs.remove(symbol)
            is_fav = False
        else:
            favs.append(symbol)
            is_fav = True
        self.favorites = favs
        self.save(update_fields=["favorites", "updated_at"])
        return is_fav

    def as_dict(self):
        return {
            "email": self.user.email,
            "username": self.user.username,
            "favorites": self.favorites or [],
            "email_alerts_enabled": self.email_alerts_enabled,
            "alert_min_quality": self.alert_min_quality,
            "alert_directions": self.alert_directions,
            "alert_favorites_only": self.alert_favorites_only,
            "alert_timeframe": self.alert_timeframe,
            "updated_at": self.updated_at.isoformat(),
        }


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_or_save_user_profile(sender, instance, created, **kwargs):
    """Automatically ensure a UserProfile exists whenever a User is created or saved."""
    default_favs = ["frxEURUSD", "stpRNG", "cryBTCUSD", "frxXAUUSD"]
    if created:
        UserProfile.objects.create(user=instance, favorites=default_favs)
    else:
        UserProfile.objects.get_or_create(user=instance, defaults={"favorites": default_favs})

