QUADCELL_ENDPOINT_CONFIG = {
    "qrysub": {
        "params": [
            {"name": "imsi", "type": "string", "required": False, "description_key": "quadcell_param_imsi"},
            {"name": "iccid", "type": "string", "required": False, "description_key": "quadcell_param_iccid"},
            {"name": "msisdn", "type": "string", "required": False, "description_key": "quadcell_param_msisdn"}
        ]
    },
    "qryusage": {
        "params": [
            {"name": "imsi", "type": "string", "required": False, "description_key": "quadcell_param_imsi"},
            {"name": "iccid", "type": "string", "required": False, "description_key": "quadcell_param_iccid"},
            {"name": "msisdn", "type": "string", "required": False, "description_key": "quadcell_param_msisdn"},
            {"name": "beginDate", "type": "string", "required": True, "description_key": "quadcell_param_beginDate"},
            {"name": "endDate", "type": "string", "required": True, "description_key": "quadcell_param_endDate"}
        ]
    },
    "qrypacklist": {
        "params": [
            {"name": "imsi", "type": "string", "required": True, "description_key": "quadcell_param_imsi"}
        ]
    },
    "qrypackquota": {
        "params": [
            {"name": "imsi", "type": "string", "required": True, "description_key": "quadcell_param_imsi"},
            {"name": "packCode", "type": "string", "required": False, "description_key": "quadcell_param_packCode"}
        ]
    },
    "qryquota": {
        "params": [
            {"name": "imsi", "type": "string", "required": True, "description_key": "quadcell_param_imsi"}
        ]
    },
    "addsub": {
        "params": [
            {"name": "imsi", "type": "string", "required": True, "description_key": "quadcell_param_imsi"},
            {"name": "iccid", "type": "string", "required": False, "description_key": "quadcell_param_iccid"},
            {"name": "msisdn", "type": "string", "required": True, "description_key": "quadcell_param_msisdn"},
            {"name": "planCode", "type": "string", "required": True, "description_key": "quadcell_param_planCode"},
            {"name": "validity", "type": "int", "required": True, "description_key": "quadcell_param_validity"},
            {"name": "lastActiveTime", "type": "string", "required": False, "description_key": "quadcell_param_lastActiveTime"},
            {"name": "initBalance", "type": "int", "required": False, "description_key": "quadcell_param_initBalance"}
        ]
    },
    "delsub": {
        "params": [
            {"name": "imsi", "type": "string", "required": True, "description_key": "quadcell_param_imsi"}
        ]
    },
    "suspend": {
        "params": [
            {"name": "imsi", "type": "string", "required": True, "description_key": "quadcell_param_imsi"},
            {"name": "serviceId", "type": "string", "required": False, "description_key": "quadcell_param_serviceId"}
        ]
    },
    "recover": {
        "params": [
            {"name": "imsi", "type": "string", "required": True, "description_key": "quadcell_param_imsi"},
            {"name": "serviceId", "type": "string", "required": False, "description_key": "quadcell_param_serviceId"}
        ]
    },
    "extend": {
        "params": [
            {"name": "imsi", "type": "string", "required": True, "description_key": "quadcell_param_imsi"},
            {"name": "append", "type": "int", "required": True, "description_key": "quadcell_param_append"},
            {"name": "noOfDays", "type": "int", "required": True, "description_key": "quadcell_param_noOfDays"}
        ]
    },
    "v2/addpack": {
        "params": [
            {"name": "imsi", "type": "string", "required": True, "description_key": "quadcell_param_imsi"},
            {"name": "packCode", "type": "string", "required": True, "description_key": "quadcell_param_packCode"},
            {"name": "activeType", "type": "string", "required": False, "description_key": "quadcell_param_activeType"},
            {"name": "activeDate", "type": "string", "required": False, "description_key": "quadcell_param_activeDate"},
            {"name": "validity", "type": "int", "required": False, "description_key": "quadcell_param_validity"}
        ]
    },
    "delpack": {
        "params": [
            {"name": "imsi", "type": "string", "required": True, "description_key": "quadcell_param_imsi"},
            {"name": "packCode", "type": "string", "required": True, "description_key": "quadcell_param_packCode"},
            {"name": "expTime", "type": "string", "required": False, "description_key": "quadcell_param_expTime"},
            {"name": "packOrderSn", "type": "string", "required": False, "description_key": "quadcell_param_packOrderSn"}
        ]
    },
    "rechargepackquota": {
        "params": [
            {"name": "imsi", "type": "string", "required": True, "description_key": "quadcell_param_imsi"},
            {"name": "packCode", "type": "string", "required": True, "description_key": "quadcell_param_packCode"},
            {"name": "rechargeQuota", "type": "int", "required": True, "description_key": "quadcell_param_rechargeQuota"},
            {"name": "packOrderSn", "type": "string", "required": False, "description_key": "quadcell_param_packOrderSn"}
        ]
    },
    "resetquota": {
        "params": [
            {"name": "imsi", "type": "string", "required": True, "description_key": "quadcell_param_imsi"},
            {"name": "packCode", "type": "string", "required": False, "description_key": "quadcell_param_packCode"},
            {"name": "packOrderSn", "type": "string", "required": False, "description_key": "quadcell_param_packOrderSn"}
        ]
    },
    "clearquota": {
        "params": [
            {"name": "imsi", "type": "string", "required": True, "description_key": "quadcell_param_imsi"},
            {"name": "packCode", "type": "string", "required": False, "description_key": "quadcell_param_packCode"},
            {"name": "packOrderSn", "type": "string", "required": False, "description_key": "quadcell_param_packOrderSn"}
        ]
    },
    "rechargequota": {
        "params": [
            {"name": "imsi", "type": "string", "required": True, "description_key": "quadcell_param_imsi"},
            {"name": "rechargeValue", "type": "int", "required": True, "description_key": "quadcell_param_rechargeValue"},
            {"name": "packCode", "type": "string", "required": False, "description_key": "quadcell_param_packCode"},
            {"name": "packOrderSn", "type": "string", "required": False, "description_key": "quadcell_param_packOrderSn"}
        ]
    },
    "addFupCode": {
        "params": [
            {"name": "imsi", "type": "string", "required": True, "description_key": "quadcell_param_imsi"},
            {"name": "packCode", "type": "string", "required": True, "description_key": "quadcell_param_packCode"},
            {"name": "fupCode", "type": "int", "required": True, "description_key": "quadcell_param_fupCode"},
            {"name": "packOrderSn", "type": "string", "required": False, "description_key": "quadcell_param_packOrderSn"}
        ]
    },
    "delFupCode": {
        "params": [
            {"name": "imsi", "type": "string", "required": True, "description_key": "quadcell_param_imsi"},
            {"name": "packCode", "type": "string", "required": True, "description_key": "quadcell_param_packCode"},
            {"name": "packOrderSn", "type": "string", "required": False, "description_key": "quadcell_param_packOrderSn"}
        ]
    },
    "cancelLoc": {
        "params": [
            {"name": "imsi", "type": "string", "required": False, "description_key": "quadcell_param_imsi"},
            {"name": "msisdn", "type": "string", "required": False, "description_key": "quadcell_param_msisdn"}
        ]
    },
    "submitsms": {
        "params": [
            {"name": "smsMt", "type": "string", "required": True, "description_key": "quadcell_param_smsMt"},
            {"name": "smsMo", "type": "string", "required": True, "description_key": "quadcell_param_smsMo"},
            {"name": "smsText", "type": "string", "required": True, "description_key": "quadcell_param_smsText"}
        ]
    },
    "qrystatus": {
        "params": [
            {"name": "iccid", "type": "string", "required": True, "description_key": "quadcell_param_iccid"}
        ]
    },
    "esim/order": {
        "params": [
            {"name": "account", "type": "string", "required": True, "description_key": "quadcell_param_account"},
            {"name": "imsiType", "type": "string", "required": True, "description_key": "quadcell_param_imsiType"},
            {"name": "planCode", "type": "string", "required": False, "description_key": "quadcell_param_planCode"},
            {"name": "lastActiveTime", "type": "string", "required": False, "description_key": "quadcell_param_lastActiveTime"},            
            {"name": "packCode", "type": "string", "required": True, "description_key": "quadcell_param_packCode"},
            {"name": "validity", "type": "int", "required": False, "description_key": "quadcell_param_validity"},
            {"name": "activeType", "type": "int", "required": False, "description_key": "quadcell_param_activeType"},
            {"name": "activeDate", "type": "string", "required": False, "description_key": "quadcell_param_activeDate"},            
            {"name": "fupCode", "type": "string", "required": False, "description_key": "quadcell_param_fupCode"}                       
        ]
    },
    "esim/qryaccount": {
        "params": [
            {"name": "account", "type": "string", "required": True, "description_key": "quadcell_param_account"}
        ]
    },
    "qryorderhistory": {
        "params": [
            {"name": "imsi", "type": "string", "required": True, "description_key": "quadcell_param_imsi"},
            {"name": "page", "type": "int", "required": False, "description_key": "quadcell_param_page"},
            {"name": "pageSize", "type": "int", "required": False, "description_key": "quadcell_param_pageSize"}
        ]
    }
}

# Quadcell端点描述映射
QUADCELL_ENDPOINT_DESCRIPTIONS = {
    "qrysub": "quadcell_endpoint_qrysub",
    "qryusage": "quadcell_endpoint_qryusage",
    "qrypacklist": "quadcell_endpoint_qrypacklist",
    "qrypackquota": "quadcell_endpoint_qrypackquota",
    "qryquota": "quadcell_endpoint_qryquota",
    "addsub": "quadcell_endpoint_addsub",
    "delsub": "quadcell_endpoint_delsub",
    "suspend": "quadcell_endpoint_suspend",
    "recover": "quadcell_endpoint_recover",
    "extend": "quadcell_endpoint_extend",
    "v2/addpack": "quadcell_endpoint_addpack",
    "delpack": "quadcell_endpoint_delpack",
    "rechargepackquota": "quadcell_endpoint_rechargepackquota",
    "resetquota": "quadcell_endpoint_resetquota",
    "clearquota": "quadcell_endpoint_clearquota",
    "rechargequota": "quadcell_endpoint_rechargequota",
    "addFupCode": "quadcell_endpoint_addFupCode",
    "delFupCode": "quadcell_endpoint_delFupCode",
    "cancelLoc": "quadcell_endpoint_cancelLoc",
    "submitsms": "quadcell_endpoint_submitsms",
    "qrystatus": "quadcell_endpoint_qrystatus",
    "esim/order": "quadcell_endpoint_esim_order",
    "esim/qryaccount": "quadcell_endpoint_esim_qryaccount",
    "qryorderhistory": "quadcell_endpoint_qryorderhistory"
}