from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = Field(default="development", alias="APP_ENV")
    debug: bool = Field(default=False, alias="DEBUG")

    # CORS
    cors_origins: str = Field(default="", alias="CORS_ORIGINS")

    # Database
    database_url: str = Field(alias="DATABASE_URL")

    # JWT
    secret_key: str = Field(alias="SECRET_KEY")
    algorithm: str = Field(default="HS256", alias="ALGORITHM")
    access_token_expire_days: int = Field(default=7, alias="ACCESS_TOKEN_EXPIRE_DAYS")

    # WeChat Mini Program
    wechat_appid: str = Field(default="", alias="WECHAT_APPID")
    wechat_secret: str = Field(default="", alias="WECHAT_SECRET")
    wechat_dev_fallback: bool = Field(default=False, alias="WECHAT_DEV_FALLBACK")

    # Tencent COS
    cos_secret_id: str = Field(default="", alias="COS_SECRET_ID")
    cos_secret_key: str = Field(default="", alias="COS_SECRET_KEY")
    cos_bucket: str = Field(default="", alias="COS_BUCKET")
    cos_region: str = Field(default="ap-guangzhou", alias="COS_REGION")
    cos_duration_seconds: int = Field(default=1800, alias="COS_DURATION_SECONDS")
    cos_allow_prefix: str = Field(default="users/*", alias="COS_ALLOW_PREFIX")

    # AI LLM
    ai_api_key: str = Field(default="", alias="AI_API_KEY")
    ai_base_url: str = Field(
        default="https://dashscope.aliyuncs.com/compatible-mode/v1", alias="AI_BASE_URL"
    )
    ai_model: str = Field(default="qwen-vl-max", alias="AI_MODEL")

    # Aliyun virtual try-on (DashScope/Bailian OutfitAnyone)
    aliyun_access_key_id: str = Field(default="", alias="ALIYUN_ACCESS_KEY_ID")
    aliyun_access_key_secret: str = Field(default="", alias="ALIYUN_ACCESS_KEY_SECRET")
    aliyun_tryon_endpoint: str = Field(
        default="https://facebody.cn-shanghai.aliyuncs.com", alias="ALIYUN_TRYON_ENDPOINT"
    )

    # DashScope/Bailian virtual try-on
    tryon_api_key: str = Field(default="", alias="TRYON_API_KEY")
    tryon_base_url: str = Field(
        default="https://dashscope.aliyuncs.com/api/v1", alias="TRYON_BASE_URL"
    )
    tryon_fast_model: str = Field(default="aitryon", alias="TRYON_FAST_MODEL")
    tryon_premium_model: str = Field(default="aitryon-plus", alias="TRYON_PREMIUM_MODEL")

    # HighwayAPI virtual try-on (default provider, fallback to Aliyun on failure)
    tryon_provider: str = Field(default="highway", alias="TRYON_PROVIDER")
    tryon_fallback_to_aliyun: bool = Field(default=True, alias="TRYON_FALLBACK_TO_ALIYUN")

    highway_api_key: str = Field(default="", alias="HIGHWAY_API_KEY")
    highway_base_url: str = Field(
        default="https://api.highwayapi.ai/v3", alias="HIGHWAY_BASE_URL"
    )
    highway_tryon_model: str = Field(default="gpt-image-2-edit", alias="HIGHWAY_TRYON_MODEL")
    highway_tryon_size: str = Field(default="1024x1024", alias="HIGHWAY_TRYON_SIZE")
    highway_tryon_quality: str = Field(default="low", alias="HIGHWAY_TRYON_QUALITY")

    # 阿里云 AI 试衣-图片分割模型，官方模型名：aitryon-parsing-v1
    tryon_segment_model: str = Field(default="aitryon-parsing-v1", alias="TRYON_SEGMENT_MODEL")
    tryon_segment_api_key: str = Field(default="", alias="TRYON_SEGMENT_API_KEY")
    tryon_segment_base_url: str = Field(
        default="https://dashscope.aliyuncs.com/api/v1", alias="TRYON_SEGMENT_BASE_URL"
    )

    # Feature gating & promotion
    feature_free_tryon_daily_limit: int = Field(default=0, alias="FEATURE_FREE_TRYON_DAILY_LIMIT")
    feature_free_puzzle_daily_limit: int = Field(default=0, alias="FEATURE_FREE_PUZZLE_DAILY_LIMIT")
    promotion_mode: bool = Field(default=False, alias="PROMOTION_MODE")

    # Credits configuration
    sign_in_reward_base: int = Field(default=5, alias="SIGN_IN_REWARD_BASE")
    sign_in_reward_max: int = Field(default=20, alias="SIGN_IN_REWARD_MAX")
    sign_in_reward_expire_days: int = Field(default=30, alias="SIGN_IN_REWARD_EXPIRE_DAYS")
    credit_purchase_expire_days: int = Field(default=60, alias="CREDIT_PURCHASE_EXPIRE_DAYS")

    # Feature credit costs (when membership quota exceeded or non-member)
    tryon_credit_cost: int = Field(default=10, alias="TRYON_CREDIT_COST")
    puzzle_credit_cost: int = Field(default=5, alias="PUZZLE_CREDIT_COST")

    # Referral rewards
    referral_register_reward_credits: int = Field(default=50, alias="REFERRAL_REGISTER_REWARD_CREDITS")
    referral_purchase_reward_credits: int = Field(default=100, alias="REFERRAL_PURCHASE_REWARD_CREDITS")


settings = Settings()
