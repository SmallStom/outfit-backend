from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = Field(default="development", alias="APP_ENV")
    debug: bool = Field(default=True, alias="DEBUG")

    # Database
    database_url: str = Field(alias="DATABASE_URL")

    # JWT
    secret_key: str = Field(alias="SECRET_KEY")
    algorithm: str = Field(default="HS256", alias="ALGORITHM")
    access_token_expire_days: int = Field(default=7, alias="ACCESS_TOKEN_EXPIRE_DAYS")

    # WeChat Mini Program
    wechat_appid: str = Field(default="", alias="WECHAT_APPID")
    wechat_secret: str = Field(default="", alias="WECHAT_SECRET")

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

    # Aliyun virtual try-on
    aliyun_access_key_id: str = Field(default="", alias="ALIYUN_ACCESS_KEY_ID")
    aliyun_access_key_secret: str = Field(default="", alias="ALIYUN_ACCESS_KEY_SECRET")
    aliyun_tryon_endpoint: str = Field(
        default="https://facebody.cn-shanghai.aliyuncs.com", alias="ALIYUN_TRYON_ENDPOINT"
    )


settings = Settings()
