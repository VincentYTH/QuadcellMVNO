WORLDMOVE_ENDPOINT_CONFIG = {
    "QuoteMg/myQueryAll": {
        "params": [
            {"name": "merchantId", "type": "string", "required": False, "description_key": "worldmove_param_merchantId"},
            {"name": "token", "type": "string", "required": False, "description_key": "worldmove_param_token"}
        ]
    },
    "SOrder/mybuyesim": {
        "params": [
            {"name": "email", "type": "string", "required": True, "description_key": "worldmove_param_email"},
            {
                "name": "prodList", 
                "type": "array", 
                "required": True, 
                "description_key": "worldmove_param_prodList",
                "fields": [
                    {"name": "wmproductId", "type": "string", "required": True, "description_key": "worldmove_param_wmproductId"},
                    {"name": "qty", "type": "number", "required": True, "description_key": "worldmove_param_qty"}
                ]
            },
            {"name": "systemMail", "type": "string", "required": False, "description_key": "worldmove_param_systemMail"}
        ]
    },
    "SOrder/querybuyesim": {
        "params": [
            {"name": "orderId", "type": "string", "required": True, "description_key": "worldmove_param_orderId"}
        ]
    },
    "SOrder/mybuyesimRedemption": {
        "params": [
            {"name": "qrcodeType", "type": "string", "required": True, "description_key": "worldmove_param_qrcodeType"},
            {
                "name": "prodList", 
                "type": "array", 
                "required": True, 
                "description_key": "worldmove_param_prodList",
                "fields": [
                    {"name": "wmproductId", "type": "string", "required": True, "description_key": "worldmove_param_wmproductId"},
                    {"name": "qty", "type": "number", "required": True, "description_key": "worldmove_param_qty"}
                ]
            }
        ]
    },
    "OrderRedemption/redemption": {
        "params": [
            {"name": "rcode", "type": "string", "required": True, "description_key": "worldmove_param_rcode"},
            {"name": "qrcodeType", "type": "string", "required": True, "description_key": "worldmove_param_qrcodeType"}
        ]
    },
    "SOrder/mybuysim": {
        "params": [
            {"name": "invoiceType", "type": "string", "required": True, "description_key": "worldmove_param_invoiceType"},
            {"name": "taxId", "type": "string", "required": True, "description_key": "worldmove_param_taxId"},
            {"name": "receivingName", "type": "string", "required": True, "description_key": "worldmove_param_receivingName"},
            {"name": "receivingTel", "type": "string", "required": True, "description_key": "worldmove_param_receivingTel"},
            {"name": "receivingAdd", "type": "string", "required": True, "description_key": "worldmove_param_receivingAdd"},
            {"name": "note", "type": "string", "required": False, "description_key": "worldmove_param_note"},
            {
                "name": "prodList", 
                "type": "array", 
                "required": True, 
                "description_key": "worldmove_param_prodList_sim",
                "fields": [
                    {"name": "productId", "type": "string", "required": True, "description_key": "worldmove_param_productId"},
                    {"name": "productName", "type": "string", "required": True, "description_key": "worldmove_param_productName"},
                    {"name": "qty", "type": "number", "required": True, "description_key": "worldmove_param_qty"}
                ]
            }
        ]
    },
    "SOrder/mydeposit": {
        "params": [
            {
                "name": "prodList", 
                "type": "array", 
                "required": True, 
                "description_key": "worldmove_param_prodList_deposit",
                "fields": [
                    {"name": "wmproductId", "type": "string", "required": True, "description_key": "worldmove_param_wmproductId"},
                    {"name": "day", "type": "number", "required": True, "description_key": "worldmove_param_day"},
                    {"name": "simNum", "type": "string", "required": True, "description_key": "worldmove_param_simNum"}
                ]
            }
        ]
    },
    "SimOperate/simRemoteActiv": {
        "params": [
            {"name": "simNum", "type": "string", "required": True, "description_key": "worldmove_param_simNum"},
            {"name": "orderId", "type": "string", "required": True, "description_key": "worldmove_param_orderId"},
            {"name": "mcc", "type": "string", "required": True, "description_key": "worldmove_param_mcc"}
        ]
    },
    "SimOperate/simTrafficReset": {
        "params": [
            {"name": "simNum", "type": "string", "required": True, "description_key": "worldmove_param_simNum"},
            {"name": "orderId", "type": "string", "required": True, "description_key": "worldmove_param_orderId"}
        ]
    },
    "UseageDetail/queryUsage": {
        "params": [
            {"name": "simNum", "type": "string", "required": True, "description_key": "worldmove_param_simNum"},
            {"name": "orderId", "type": "string", "required": True, "description_key": "worldmove_param_orderId"}
        ]
    },
    "UseageDetail/queryBasicInfo": {
        "params": [
            {"name": "rcode", "type": "string", "required": True, "description_key": "worldmove_param_rcode"}
        ]
    },
    "UseageDetail/queryEsimProgresses": {
        "params": [
            {"name": "rcode", "type": "string", "required": True, "description_key": "worldmove_param_rcode"}
        ]
    },
    "SimQuery/simExists": {
        "params": [
            {"name": "simNum", "type": "string", "required": True, "description_key": "worldmove_param_simNum"}
        ]
    }
}

# WorldMove端点描述映射
WORLDMOVE_ENDPOINT_DESCRIPTIONS = {
    "QuoteMg/myQueryAll": "worldmove_endpoint_quote_query_all",
    "SOrder/mybuyesim": "worldmove_endpoint_buy_esim",
    "SOrder/querybuyesim": "worldmove_endpoint_query_esim",
    "SOrder/mybuyesimRedemption": "worldmove_endpoint_buy_esim_redemption",
    "OrderRedemption/redemption": "worldmove_endpoint_redemption",
    "SOrder/mybuysim": "worldmove_endpoint_buy_sim",
    "SOrder/mydeposit": "worldmove_endpoint_deposit",
    "SimOperate/simRemoteActiv": "worldmove_endpoint_sim_remote_activ",
    "SimOperate/simTrafficReset": "worldmove_endpoint_sim_traffic_reset",
    "UseageDetail/queryUsage": "worldmove_endpoint_query_usage",
    "UseageDetail/queryBasicInfo": "worldmove_endpoint_query_basic_info",
    "UseageDetail/queryEsimProgresses": "worldmove_endpoint_query_esim_progresses",
    "SimQuery/simExists": "worldmove_endpoint_sim_exists"
}

# WorldMove端点加密配置（包含签名计算规则）
WORLDMOVE_ENCRYPTION_CONFIG = {
    "QuoteMg/myQueryAll": {
        "enc_params": ["merchantId", "token"],
        "non_enc_params": []
    },
    "SOrder/mybuyesim": {
        "enc_params": ["merchantId", "prodList", "token"],
        "prodList_format": "wmproductId+qty",
        "non_enc_params": ["email", "systemMail"]
    },
    "SOrder/querybuyesim": {
        "enc_params": ["merchantId", "orderId", "token"],
        "non_enc_params": []
    },
    "SOrder/mybuyesimRedemption": {
        "enc_params": ["merchantId", "prodList", "token"],
        "prodList_format": "wmproductId+qty",
        "non_enc_params": ["qrcodeType"]
    },
    "OrderRedemption/redemption": {
        "enc_params": ["merchantId", "rcode", "token"],
        "non_enc_params": ["qrcodeType"]
    },
    "SOrder/mybuysim": {
        "enc_params": ["merchantId", "prodList", "token"],
        "prodList_format": "productid+productName+qty",
        "non_enc_params": ["invoiceType", "taxId", "receivingName", "receivingTel", "receivingAdd", "note"]
    },
    "SOrder/mydeposit": {
        "enc_params": ["merchantId", "prodList", "token"],
        "prodList_format": "wmproductId+day+simNum",
        "non_enc_params": []
    },
    "SimOperate/simRemoteActiv": {
        "enc_params": ["merchantId", "simNum", "orderId", "mcc", "token"],
        "non_enc_params": []
    },
    "SimOperate/simTrafficReset": {
        "enc_params": ["merchantId", "simNum", "orderId", "token"],
        "non_enc_params": []
    },
    "UseageDetail/queryUsage": {
        "enc_params": ["merchantId", "simNum", "orderId", "token"],
        "non_enc_params": []
    },
    "UseageDetail/queryBasicInfo": {
        "enc_params": ["merchantId", "rcode", "token"],
        "non_enc_params": []
    },
    "UseageDetail/queryEsimProgresses": {
        "enc_params": ["merchantId", "rcode", "token"],
        "non_enc_params": []
    },
    "SimQuery/simExists": {
        "enc_params": ["merchantId", "simNum", "token"],
        "non_enc_params": []
    }
}