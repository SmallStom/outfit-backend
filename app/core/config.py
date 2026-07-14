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
    # DashScope native API (multimodal embedding / other non-OpenAI-compatible services)
    ai_dashscope_base_url: str = Field(
        default="https://dashscope.aliyuncs.com/api/v1", alias="AI_DASHSCOPE_BASE_URL"
    )

    # DashScope/Bailian virtual try-on
    tryon_api_key: str = Field(default="", alias="TRYON_API_KEY")
    tryon_base_url: str = Field(
        default="https://dashscope.aliyuncs.com/api/v1", alias="TRYON_BASE_URL"
    )
    tryon_fast_model: str = Field(default="aitryon", alias="TRYON_FAST_MODEL")
    tryon_premium_model: str = Field(default="aitryon-plus", alias="TRYON_PREMIUM_MODEL")

    # 图片编辑 API（OpenAI 兼容 images/edits，试穿 + 衣物提取共用）
    tryon_provider: str = Field(default="image_edit", alias="TRYON_PROVIDER")
    tryon_fallback_to_aliyun: bool = Field(default=True, alias="TRYON_FALLBACK_TO_ALIYUN")

    image_edit_base_url: str = Field(
        default="https://www.dmxapi.cn/v1", alias="IMAGE_EDIT_BASE_URL"
    )
    image_edit_api_key: str = Field(default="", alias="IMAGE_EDIT_API_KEY")
    image_edit_model: str = Field(default="gpt-image-1", alias="IMAGE_EDIT_MODEL")
    image_edit_quality: str = Field(default="low", alias="IMAGE_EDIT_QUALITY")
    image_edit_size: str = Field(default="1024x1024", alias="IMAGE_EDIT_SIZE")

    # 批量导入
    batch_import_concurrency: int = Field(default=3, alias="BATCH_IMPORT_CONCURRENCY")
    batch_import_max_files: int = Field(default=20, alias="BATCH_IMPORT_MAX_FILES")

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

    # Recommendation models
    ai_attribute_model: str = Field(default="qwen3.7-plus", alias="AI_ATTRIBUTE_MODEL")
    ai_embedding_model: str = Field(
        default="tongyi-embedding-vision-flash-2026-03-06", alias="AI_EMBEDDING_MODEL"
    )
    ai_rerank_model: str = Field(default="qwen3.7-plus", alias="AI_RERANK_MODEL")
    ai_embedding_dim: int = Field(default=768, alias="AI_EMBEDDING_DIM")
    ai_image_allowed_hosts: str = Field(default="", alias="AI_IMAGE_ALLOWED_HOSTS")

    # Recommendation scoring weights (V2: 六维融合)
    reco_weight_style: float = Field(default=0.25, alias="RECO_WEIGHT_STYLE")
    reco_weight_color: float = Field(default=0.25, alias="RECO_WEIGHT_COLOR")
    reco_weight_occasion: float = Field(default=0.15, alias="RECO_WEIGHT_OCCASION")
    reco_weight_weather: float = Field(default=0.10, alias="RECO_WEIGHT_WEATHER")
    reco_weight_bias: float = Field(default=0.10, alias="RECO_WEIGHT_BIAS")
    reco_top_k: int = Field(default=3, alias="RECO_TOP_K")
    reco_candidate_k: int = Field(default=10, alias="RECO_CANDIDATE_K")
    # 大规模候选预筛选：上装随机采样数 + 每个上装的 top-M 下装候选
    reco_prefilter_top_n: int = Field(default=15, alias="RECO_PREFILTER_TOP_N")
    reco_prefilter_bottom_m: int = Field(default=15, alias="RECO_PREFILTER_BOTTOM_M")
    reco_prefilter_standalone_n: int = Field(default=10, alias="RECO_PREFILTER_STANDALONE_N")
    # 预筛选触发的候选数量阈值（上装×下装超过此值时启用预筛选）
    reco_prefilter_threshold: int = Field(default=200, alias="RECO_PREFILTER_THRESHOLD")
    reco_shop_top_k: int = Field(default=5, alias="RECO_SHOP_TOP_K")
    reco_cache_ttl_minutes: int = Field(default=120, alias="RECO_CACHE_TTL_MINUTES")
    reco_min_interval_seconds: int = Field(default=30, alias="RECO_MIN_INTERVAL_SECONDS")

    # V2 新增评分维度权重
    reco_weight_silhouette: float = Field(default=0.15, alias="RECO_WEIGHT_SILHOUETTE")
    reco_weight_preference: float = Field(default=0.10, alias="RECO_WEIGHT_PREFERENCE")
    # 避免重复推荐惩罚
    reco_worn_within_days: int = Field(default=7, alias="RECO_WORN_WITHIN_DAYS")
    reco_worn_penalty: float = Field(default=0.20, alias="RECO_WORN_PENALTY")
    reco_repeat_days: int = Field(default=3, alias="RECO_REPEAT_DAYS")
    reco_repeat_threshold: int = Field(default=3, alias="RECO_REPEAT_THRESHOLD")
    reco_repeat_penalty: float = Field(default=0.15, alias="RECO_REPEAT_PENALTY")
    # 偏好学习融合权重
    reco_preference_blend: float = Field(default=0.25, alias="RECO_PREFERENCE_BLEND")
    # V2 算法开关（true=V2, false=V1）
    reco_use_v2: bool = Field(default=True, alias="RECO_USE_V2")

    # Tencent Map / Location Service
    tencent_map_key: str = Field(default="", alias="TENCENT_MAP_KEY")
    tencent_map_host: str = Field(default="https://apis.map.qq.com", alias="TENCENT_MAP_HOST")
    tencent_map_weather_cache_minutes: int = Field(default=120, alias="TENCENT_MAP_WEATHER_CACHE_MINUTES")

    # Phase 7: 真人试穿增强 - 多适配器 API Key（V3.2，可选配置）
    tryon_outfitanyone_api_key: str = Field(default="", alias="TRYON_OUTFITANYONE_API_KEY")
    tryon_idmvton_api_key: str = Field(default="", alias="TRYON_IDMVTON_API_KEY")
    tryon_idmvton_base_url: str = Field(
        default="https://idm-vton.example.com/api", alias="TRYON_IDMVTON_BASE_URL"
    )
    tryon_catvton_api_key: str = Field(default="", alias="TRYON_CATVTON_API_KEY")
    tryon_catvton_base_url: str = Field(
        default="https://cat-vton.example.com/api", alias="TRYON_CATVTON_BASE_URL"
    )


settings = Settings()
