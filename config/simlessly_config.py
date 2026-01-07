SIMLESSLY_ENDPOINT_CONFIG = {
    "profile/detail": {
        "params": [
            {
                "name": "iccid",
                "type": "string",
                "required": True,
                "description_key": "simlessly_param_iccid"
            }
        ]
    },
    "profile/log": {
        "params": [
            {
                "name": "iccid",
                "type": "string",
                "required": True,
                "description_key": "simlessly_param_iccid"
            },
            {
                "name": "pageParam.pageNum",
                "type": "integer", 
                "required": True,
                "description_key": "simlessly_param_pageParam_pageNum"
            },
            {
                "name": "pageParam.pageSize",
                "type": "integer",
                "required": True,
                "description_key": "simlessly_param_pageParam_pageSize"
            }
        ]
    },
    "profile/delete": {
        "params": [
            {
                "name": "iccid",
                "type": "string",
                "required": True,
                "description_key": "simlessly_param_iccid"
            }            
        ]
    },
    "profile/updateParam": {
        "params": [
            {
                "name": "iccid",
                "type": "string",
                "required": True,
                "description_key": "simlessly_param_iccid"
            },
            {
                "name": "imsi",
                "type": "string",
                "required": True,
                "description_key": "simlessly_param_imsi"
            },                
            {
                "name": "msisdn",
                "type": "string",
                "required": False,
                "description_key": "simlessly_param_msisdn"
            },
            {
                "name": "ki",
                "type": "string",
                "required": False,
                "description_key": "simlessly_param_ki"
            },
            {
                "name": "opc",
                "type": "string",
                "required": False,
                "description_key": "simlessly_param_opc"
            },
            {
                "name": "spn",
                "type": "string",
                "required": False,
                "description_key": "simlessly_param_spn"
            }                    
        ]
    },    
    "ac/generate": {
        "params": [
            {
                "name": "iccid",
                "type": "string",
                "required": True,
                "description_key": "simlessly_param_iccid"
            },
            {
                "name": "imsi",
                "type": "string",
                "required": True,
                "description_key": "simlessly_param_imsi"
            },
            {
                "name": "ki",
                "type": "string",
                "required": True,
                "description_key": "simlessly_param_ki"
            },
            {
                "name": "opc",
                "type": "string",
                "required": True,
                "description_key": "simlessly_param_opc"
            },
            {
                "name": "configName",
                "type": "string",
                "required": True,
                "description_key": "simlessly_param_configName"
            },
            {
                "name": "msisdn",
                "type": "string",
                "required": False,
                "description_key": "simlessly_param_msisdn"
            },
            {
                "name": "spn",
                "type": "string",
                "required": False,
                "description_key": "simlessly_param_spn"
            },
            {
                "name": "expireTime",
                "type": "string",
                "required": False,
                "description_key": "simlessly_param_expireTime"
            },
            # {
            #     "name": "hplmnList",
            #     "type": "string",
            #     "required": False,
            #     "description_key": "simlessly_param_hplmnList"
            # },
            # {
            #     "name": "ehplmnList", 
            #     "type": "string",
            #     "required": False,
            #     "description_key": "simlessly_param_ehplmnList"
            # },
            # {
            #     "name": "oplmnList",
            #     "type": "string",
            #     "required": False,
            #     "description_key": "simlessly_param_oplmnList"
            # },
            # {
            #     "name": "fplmnList",
            #     "type": "string",
            #     "required": False,
            #     "description_key": "simlessly_param_fplmnList"
            # },
            {
                "name": "pin1",
                "type": "string",
                "required": False,
                "description_key": "simlessly_param_pin1"
            },
            {
                "name": "pin2",
                "type": "string",
                "required": False,
                "description_key": "simlessly_param_pin2"
            },
            {
                "name": "puk1",
                "type": "string",
                "required": False,
                "description_key": "simlessly_param_puk1"
            },
            {
                "name": "puk2",
                "type": "string",
                "required": False,
                "description_key": "simlessly_param_puk2"
            },
            {
                "name": "multiImsiDataList",
                "type": "array",
                "required": False,
                "description_key": "simlessly_param_multiImsiDataList"
            }
        ]
    }        
}

# Simlessly端点描述映射
SIMLESSLY_ENDPOINT_DESCRIPTIONS = {
    "profile/detail": "simlessly_endpoint_profile_detail",
    "profile/log": "simlessly_endpoint_profile_log", 
    "profile/delete": "simlessly_endpoint_profile_delete",
    "profile/updateParam": "simlessly_endpoint_profile_updateParam",    
    "ac/generate": "simlessly_endpoint_ac_generate"
}