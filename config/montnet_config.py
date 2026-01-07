MONTNET_ENDPOINT_CONFIG = {
    "heartbeat": {
        "params": [
            {
                "name": "authKey",
                "type": "string",
                "required": False,
                "description_key": "montnet_param_authKey"
            }
        ]
    },
    "qrysub": {
        "params": [
            {
                "name": "imsi",
                "type": "string",
                "required": False,
                "description_key": "montnet_param_imsi"
            },
            {
                "name": "iccid",
                "type": "string",
                "required": False,
                "description_key": "montnet_param_iccid"
            },
            {
                "name": "msisdn",
                "type": "string",
                "required": False,
                "description_key": "montnet_param_msisdn"
            }
        ]
    },
    "qrypacklist": {
        "params": [
            {
                "name": "imsi",
                "type": "string",
                "required": False,
                "description_key": "montnet_param_imsi"
            },
            {
                "name": "iccid",
                "type": "string",
                "required": False,
                "description_key": "montnet_param_iccid"
            },
            {
                "name": "msisdn",
                "type": "string",
                "required": False,
                "description_key": "montnet_param_msisdn"
            },
            {
                "name": "productId",
                "type": "string",
                "required": False,
                "description_key": "montnet_param_productId"
            },
            {
                "name": "subscriptionId",
                "type": "string",
                "required": False,
                "description_key": "montnet_param_subscriptionId"
            }
        ]
    },
    "queryQosQuota": {
        "params": [
            {
                "name": "imsi",
                "type": "string",
                "required": False,
                "description_key": "montnet_param_imsi"
            },
            {
                "name": "iccid",
                "type": "string",
                "required": False,
                "description_key": "montnet_param_iccid"
            },
            {
                "name": "msisdn",
                "type": "string",
                "required": False,
                "description_key": "montnet_param_msisdn"
            },
            {
                "name": "productId",
                "type": "string",
                "required": False,
                "description_key": "montnet_param_productId"
            },
            {
                "name": "subscriptionId",
                "type": "string",
                "required": False,
                "description_key": "montnet_param_subscriptionId"
            }
        ]
    },        
    "addpack": {
        "params": [
            {
                "name": "imsi",
                "type": "string",
                "required": False,
                "description_key": "montnet_param_imsi"
            },
            {
                "name": "iccid",
                "type": "string",
                "required": False,
                "description_key": "montnet_param_iccid"
            },
            {
                "name": "msisdn",
                "type": "string",
                "required": False,
                "description_key": "montnet_param_msisdn"
            },
            {
                "name": "packCode",
                "type": "string",
                "required": True,
                "description_key": "montnet_param_packCode"
            }
        ]
    },
    "delpack": {
        "params": [
            {
                "name": "imsi",
                "type": "string",
                "required": False,
                "description_key": "montnet_param_imsi"
            },
            {
                "name": "iccid",
                "type": "string",
                "required": False,
                "description_key": "montnet_param_iccid"
            },
            {
                "name": "msisdn",
                "type": "string",
                "required": False,
                "description_key": "montnet_param_msisdn"
            },
            {
                "name": "packCode",
                "type": "string",
                "required": True,
                "description_key": "montnet_param_packCode"
            }
        ]
    },
    "quota/topup": {
        "params": [
            {
                "name": "imsi",
                "type": "string",
                "required": False,
                "description_key": "montnet_param_imsi"
            },
            {
                "name": "iccid",
                "type": "string",
                "required": False,
                "description_key": "montnet_param_iccid"
            },
            {
                "name": "msisdn",
                "type": "string",
                "required": False,
                "description_key": "montnet_param_msisdn"
            },
            {
                "name": "subscriptionId",
                "type": "string",
                "required": True,
                "description_key": "montnet_param_subscriptionId"
            },
            {
                "name": "quota",
                "type": "string",
                "required": True,
                "description_key": "montnet_param_quota"
            }                
        ]
    },        
    "suspend": {
        "params": [
            {
                "name": "imsi",
                "type": "string",
                "required": False,
                "description_key": "montnet_param_imsi"
            },
            {
                "name": "iccid",
                "type": "string",
                "required": False,
                "description_key": "montnet_param_iccid"
            },
            {
                "name": "msisdn",
                "type": "string",
                "required": False,
                "description_key": "montnet_param_msisdn"
            }               
        ]
    },
    "recover": {
        "params": [
            {
                "name": "imsi",
                "type": "string",
                "required": False,
                "description_key": "montnet_param_imsi"
            },
            {
                "name": "iccid",
                "type": "string",
                "required": False,
                "description_key": "montnet_param_iccid"
            },
            {
                "name": "msisdn",
                "type": "string",
                "required": False,
                "description_key": "montnet_param_msisdn"
            }               
        ]
    },
    "qryLocation": {
        "params": [
            {
                "name": "imsi",
                "type": "string",
                "required": False,
                "description_key": "montnet_param_imsi"
            },
            {
                "name": "iccid",
                "type": "string",
                "required": False,
                "description_key": "montnet_param_iccid"
            },
            {
                "name": "msisdn",
                "type": "string",
                "required": False,
                "description_key": "montnet_param_msisdn"
            }               
        ]
    }                      
}

# MontNet端点描述映射
MONTNET_ENDPOINT_DESCRIPTIONS = {
    "heartbeat": "montnet_endpoint_heartbeat",
    "qrysub": "montnet_endpoint_qrysub", 
    "qrypacklist": "montnet_endpoint_qrypacklist",
    "queryQosQuota": "montnet_endpoint_queryQosQuota",
    "addpack": "montnet_endpoint_addpack",
    "delpack": "montnet_endpoint_delpack",
    "quota/topup": "montnet_endpoint_quota_topup",
    "suspend": "montnet_endpoint_suspend",
    "recover": "montnet_endpoint_recover",
    "qryLocation": "montnet_endpoint_qryLocation"  
}