from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Primitive(_message.Message):
    __slots__ = ("op", "to", "fr", "rqi", "ty", "rvi", "rsc", "ot", "rqet", "drt", "rcn", "ext", "ae", "cnt", "cin", "sub", "sgn", "dbg", "pc_json")
    OP_FIELD_NUMBER: _ClassVar[int]
    TO_FIELD_NUMBER: _ClassVar[int]
    FR_FIELD_NUMBER: _ClassVar[int]
    RQI_FIELD_NUMBER: _ClassVar[int]
    TY_FIELD_NUMBER: _ClassVar[int]
    RVI_FIELD_NUMBER: _ClassVar[int]
    RSC_FIELD_NUMBER: _ClassVar[int]
    OT_FIELD_NUMBER: _ClassVar[int]
    RQET_FIELD_NUMBER: _ClassVar[int]
    DRT_FIELD_NUMBER: _ClassVar[int]
    RCN_FIELD_NUMBER: _ClassVar[int]
    EXT_FIELD_NUMBER: _ClassVar[int]
    AE_FIELD_NUMBER: _ClassVar[int]
    CNT_FIELD_NUMBER: _ClassVar[int]
    CIN_FIELD_NUMBER: _ClassVar[int]
    SUB_FIELD_NUMBER: _ClassVar[int]
    SGN_FIELD_NUMBER: _ClassVar[int]
    DBG_FIELD_NUMBER: _ClassVar[int]
    PC_JSON_FIELD_NUMBER: _ClassVar[int]
    op: int
    to: str
    fr: str
    rqi: str
    ty: int
    rvi: str
    rsc: int
    ot: int
    rqet: int
    drt: int
    rcn: int
    ext: bytes
    ae: AE
    cnt: Container
    cin: ContentInstance
    sub: Subscription
    sgn: Notification
    dbg: str
    pc_json: bytes
    def __init__(self, op: _Optional[int] = ..., to: _Optional[str] = ..., fr: _Optional[str] = ..., rqi: _Optional[str] = ..., ty: _Optional[int] = ..., rvi: _Optional[str] = ..., rsc: _Optional[int] = ..., ot: _Optional[int] = ..., rqet: _Optional[int] = ..., drt: _Optional[int] = ..., rcn: _Optional[int] = ..., ext: _Optional[bytes] = ..., ae: _Optional[_Union[AE, _Mapping]] = ..., cnt: _Optional[_Union[Container, _Mapping]] = ..., cin: _Optional[_Union[ContentInstance, _Mapping]] = ..., sub: _Optional[_Union[Subscription, _Mapping]] = ..., sgn: _Optional[_Union[Notification, _Mapping]] = ..., dbg: _Optional[str] = ..., pc_json: _Optional[bytes] = ...) -> None: ...

class AE(_message.Message):
    __slots__ = ("rn", "ri", "pi", "ty", "ct", "lt", "et", "lbl", "acpi", "api", "aei", "rr", "srv", "poa", "ext", "csz")
    RN_FIELD_NUMBER: _ClassVar[int]
    RI_FIELD_NUMBER: _ClassVar[int]
    PI_FIELD_NUMBER: _ClassVar[int]
    TY_FIELD_NUMBER: _ClassVar[int]
    CT_FIELD_NUMBER: _ClassVar[int]
    LT_FIELD_NUMBER: _ClassVar[int]
    ET_FIELD_NUMBER: _ClassVar[int]
    LBL_FIELD_NUMBER: _ClassVar[int]
    ACPI_FIELD_NUMBER: _ClassVar[int]
    API_FIELD_NUMBER: _ClassVar[int]
    AEI_FIELD_NUMBER: _ClassVar[int]
    RR_FIELD_NUMBER: _ClassVar[int]
    SRV_FIELD_NUMBER: _ClassVar[int]
    POA_FIELD_NUMBER: _ClassVar[int]
    EXT_FIELD_NUMBER: _ClassVar[int]
    CSZ_FIELD_NUMBER: _ClassVar[int]
    rn: str
    ri: str
    pi: str
    ty: int
    ct: int
    lt: int
    et: int
    lbl: _containers.RepeatedScalarFieldContainer[str]
    acpi: _containers.RepeatedScalarFieldContainer[str]
    api: str
    aei: str
    rr: bool
    srv: _containers.RepeatedScalarFieldContainer[str]
    poa: _containers.RepeatedScalarFieldContainer[str]
    ext: bytes
    csz: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, rn: _Optional[str] = ..., ri: _Optional[str] = ..., pi: _Optional[str] = ..., ty: _Optional[int] = ..., ct: _Optional[int] = ..., lt: _Optional[int] = ..., et: _Optional[int] = ..., lbl: _Optional[_Iterable[str]] = ..., acpi: _Optional[_Iterable[str]] = ..., api: _Optional[str] = ..., aei: _Optional[str] = ..., rr: _Optional[bool] = ..., srv: _Optional[_Iterable[str]] = ..., poa: _Optional[_Iterable[str]] = ..., ext: _Optional[bytes] = ..., csz: _Optional[_Iterable[str]] = ...) -> None: ...

class Container(_message.Message):
    __slots__ = ("rn", "ri", "pi", "ty", "ct", "lt", "et", "lbl", "acpi", "st", "mni", "mbs", "cni", "cbs", "ext", "mia", "cr")
    RN_FIELD_NUMBER: _ClassVar[int]
    RI_FIELD_NUMBER: _ClassVar[int]
    PI_FIELD_NUMBER: _ClassVar[int]
    TY_FIELD_NUMBER: _ClassVar[int]
    CT_FIELD_NUMBER: _ClassVar[int]
    LT_FIELD_NUMBER: _ClassVar[int]
    ET_FIELD_NUMBER: _ClassVar[int]
    LBL_FIELD_NUMBER: _ClassVar[int]
    ACPI_FIELD_NUMBER: _ClassVar[int]
    ST_FIELD_NUMBER: _ClassVar[int]
    MNI_FIELD_NUMBER: _ClassVar[int]
    MBS_FIELD_NUMBER: _ClassVar[int]
    CNI_FIELD_NUMBER: _ClassVar[int]
    CBS_FIELD_NUMBER: _ClassVar[int]
    EXT_FIELD_NUMBER: _ClassVar[int]
    MIA_FIELD_NUMBER: _ClassVar[int]
    CR_FIELD_NUMBER: _ClassVar[int]
    rn: str
    ri: str
    pi: str
    ty: int
    ct: int
    lt: int
    et: int
    lbl: _containers.RepeatedScalarFieldContainer[str]
    acpi: _containers.RepeatedScalarFieldContainer[str]
    st: int
    mni: int
    mbs: int
    cni: int
    cbs: int
    ext: bytes
    mia: int
    cr: str
    def __init__(self, rn: _Optional[str] = ..., ri: _Optional[str] = ..., pi: _Optional[str] = ..., ty: _Optional[int] = ..., ct: _Optional[int] = ..., lt: _Optional[int] = ..., et: _Optional[int] = ..., lbl: _Optional[_Iterable[str]] = ..., acpi: _Optional[_Iterable[str]] = ..., st: _Optional[int] = ..., mni: _Optional[int] = ..., mbs: _Optional[int] = ..., cni: _Optional[int] = ..., cbs: _Optional[int] = ..., ext: _Optional[bytes] = ..., mia: _Optional[int] = ..., cr: _Optional[str] = ...) -> None: ...

class ContentInstance(_message.Message):
    __slots__ = ("rn", "ri", "pi", "ty", "ct", "lt", "et", "lbl", "cnf", "con", "cs", "st", "cr", "ext")
    RN_FIELD_NUMBER: _ClassVar[int]
    RI_FIELD_NUMBER: _ClassVar[int]
    PI_FIELD_NUMBER: _ClassVar[int]
    TY_FIELD_NUMBER: _ClassVar[int]
    CT_FIELD_NUMBER: _ClassVar[int]
    LT_FIELD_NUMBER: _ClassVar[int]
    ET_FIELD_NUMBER: _ClassVar[int]
    LBL_FIELD_NUMBER: _ClassVar[int]
    CNF_FIELD_NUMBER: _ClassVar[int]
    CON_FIELD_NUMBER: _ClassVar[int]
    CS_FIELD_NUMBER: _ClassVar[int]
    ST_FIELD_NUMBER: _ClassVar[int]
    CR_FIELD_NUMBER: _ClassVar[int]
    EXT_FIELD_NUMBER: _ClassVar[int]
    rn: str
    ri: str
    pi: str
    ty: int
    ct: int
    lt: int
    et: int
    lbl: _containers.RepeatedScalarFieldContainer[str]
    cnf: str
    con: str
    cs: int
    st: int
    cr: str
    ext: bytes
    def __init__(self, rn: _Optional[str] = ..., ri: _Optional[str] = ..., pi: _Optional[str] = ..., ty: _Optional[int] = ..., ct: _Optional[int] = ..., lt: _Optional[int] = ..., et: _Optional[int] = ..., lbl: _Optional[_Iterable[str]] = ..., cnf: _Optional[str] = ..., con: _Optional[str] = ..., cs: _Optional[int] = ..., st: _Optional[int] = ..., cr: _Optional[str] = ..., ext: _Optional[bytes] = ...) -> None: ...

class Subscription(_message.Message):
    __slots__ = ("rn", "ri", "pi", "ty", "ct", "lt", "et", "lbl", "acpi", "nu", "net", "nct", "cr", "exc", "ext")
    RN_FIELD_NUMBER: _ClassVar[int]
    RI_FIELD_NUMBER: _ClassVar[int]
    PI_FIELD_NUMBER: _ClassVar[int]
    TY_FIELD_NUMBER: _ClassVar[int]
    CT_FIELD_NUMBER: _ClassVar[int]
    LT_FIELD_NUMBER: _ClassVar[int]
    ET_FIELD_NUMBER: _ClassVar[int]
    LBL_FIELD_NUMBER: _ClassVar[int]
    ACPI_FIELD_NUMBER: _ClassVar[int]
    NU_FIELD_NUMBER: _ClassVar[int]
    NET_FIELD_NUMBER: _ClassVar[int]
    NCT_FIELD_NUMBER: _ClassVar[int]
    CR_FIELD_NUMBER: _ClassVar[int]
    EXC_FIELD_NUMBER: _ClassVar[int]
    EXT_FIELD_NUMBER: _ClassVar[int]
    rn: str
    ri: str
    pi: str
    ty: int
    ct: int
    lt: int
    et: int
    lbl: _containers.RepeatedScalarFieldContainer[str]
    acpi: _containers.RepeatedScalarFieldContainer[str]
    nu: _containers.RepeatedScalarFieldContainer[str]
    net: _containers.RepeatedScalarFieldContainer[int]
    nct: int
    cr: str
    exc: int
    ext: bytes
    def __init__(self, rn: _Optional[str] = ..., ri: _Optional[str] = ..., pi: _Optional[str] = ..., ty: _Optional[int] = ..., ct: _Optional[int] = ..., lt: _Optional[int] = ..., et: _Optional[int] = ..., lbl: _Optional[_Iterable[str]] = ..., acpi: _Optional[_Iterable[str]] = ..., nu: _Optional[_Iterable[str]] = ..., net: _Optional[_Iterable[int]] = ..., nct: _Optional[int] = ..., cr: _Optional[str] = ..., exc: _Optional[int] = ..., ext: _Optional[bytes] = ...) -> None: ...

class Notification(_message.Message):
    __slots__ = ("net", "ae", "cnt", "cin", "sub", "sur", "vrq", "cr", "ext")
    NET_FIELD_NUMBER: _ClassVar[int]
    AE_FIELD_NUMBER: _ClassVar[int]
    CNT_FIELD_NUMBER: _ClassVar[int]
    CIN_FIELD_NUMBER: _ClassVar[int]
    SUB_FIELD_NUMBER: _ClassVar[int]
    SUR_FIELD_NUMBER: _ClassVar[int]
    VRQ_FIELD_NUMBER: _ClassVar[int]
    CR_FIELD_NUMBER: _ClassVar[int]
    EXT_FIELD_NUMBER: _ClassVar[int]
    net: int
    ae: AE
    cnt: Container
    cin: ContentInstance
    sub: Subscription
    sur: str
    vrq: bool
    cr: str
    ext: bytes
    def __init__(self, net: _Optional[int] = ..., ae: _Optional[_Union[AE, _Mapping]] = ..., cnt: _Optional[_Union[Container, _Mapping]] = ..., cin: _Optional[_Union[ContentInstance, _Mapping]] = ..., sub: _Optional[_Union[Subscription, _Mapping]] = ..., sur: _Optional[str] = ..., vrq: _Optional[bool] = ..., cr: _Optional[str] = ..., ext: _Optional[bytes] = ...) -> None: ...
