"""Real primitives captured from ACME 2026.05.1 (JSON over MQTT), used by codec tests and benchmarks."""

AE_CREATE = {"op": 1, "to": "cse-in", "fr": "Cprobe", "rqi": "816850ac", "rvi": "5", "ty": 2,
             "pc": {"m2m:ae": {"rn": "probeAE", "api": "Nprobe", "rr": True, "srv": ["5"],
                               "poa": ["mqtt://127.0.0.1:1883"]}}}
AE_CREATED = {"fr": "/id-in", "to": "Cprobe", "ot": "20261110T214309,619493", "rsc": 2001, "rqi": "816850ac",
              "rvi": "5", "drt": 1,
              "pc": {"m2m:ae": {"rn": "probeAE", "api": "Nprobe", "rr": True, "srv": ["5"],
                                "poa": ["mqtt://127.0.0.1:1883"], "pi": "id-in", "ri": "Cprobe", "ty": 2,
                                "aei": "Cprobe", "ct": "20261110T214309,616030", "lt": "20261110T214309,616030",
                                "et": "20311109T214309,617978"}}}
CNT_CREATED = {"fr": "/id-in", "to": "Cprobe", "ot": "20261110T214309,637591", "rsc": 2001, "rqi": "89fe9f38",
               "rvi": "5", "drt": 1,
               "pc": {"m2m:cnt": {"rn": "temp", "mni": 100, "cni": 0, "cbs": 0, "st": 0, "pi": "Cprobe",
                                  "ri": "cnt5OY01h7geE", "ty": 3, "ct": "20261110T214309,627055",
                                  "lt": "20261110T214309,627055", "et": "20311109T214309,617978"}}}
SUB_CREATE = {"op": 1, "to": "cse-in/probeAE/temp", "fr": "Cprobe", "rqi": "6fbe4497", "rvi": "5", "ty": 23,
              "pc": {"m2m:sub": {"rn": "sub", "nu": ["Cprobe"], "enc": {"net": [3]}}}}
CIN_CREATE = {"op": 1, "to": "cse-in/probeAE/temp", "fr": "Cprobe", "rqi": "d1b39b0b", "rvi": "5", "ty": 4,
              "pc": {"m2m:cin": {"cnf": "text/plain:0", "con": "23.5"}}}
CIN_CREATED = {"fr": "/id-in", "to": "Cprobe", "ot": "20261110T214310,180414", "rsc": 2001, "rqi": "d1b39b0b",
               "rvi": "5", "drt": 1,
               "pc": {"m2m:cin": {"cnf": "text/plain:0", "con": "23.5", "cs": 4, "pi": "cnt5OY01h7geE",
                                  "ri": "cinNcxs5EWMjD", "rn": "cin_ELz4wirhsr", "ty": 4,
                                  "ct": "20261110T214310,165062", "lt": "20261110T214310,165062",
                                  "et": "20311109T214309,617978", "st": 1}}}
NOTIFY = {"fr": "/id-in", "to": "Cprobe", "ot": "20261110T214310,175712", "op": 5, "rqi": "cvIVZ7Oh5j", "rvi": "5",
          "drt": 1,
          "pc": {"m2m:sgn": {"nev": {"net": 3, "rep": {"m2m:cin": {
              "cnf": "text/plain:0", "con": "23.5", "cs": 4, "pi": "cnt5OY01h7geE", "ri": "cinNcxs5EWMjD",
              "rn": "cin_ELz4wirhsr", "ty": 4, "ct": "20261110T214310,165062", "lt": "20261110T214310,165062",
              "et": "20311109T214309,617978", "st": 1}}}, "sur": "/id-in/subrMsvA2i56y"}}}
RETRIEVE_LA = {"op": 2, "to": "cse-in/probeAE/temp/la", "fr": "Cprobe", "rqi": "27cd4f2f", "rvi": "5"}
CNT_UPDATED = {"fr": "/id-in", "to": "Cprobe", "ot": "20261110T214311,210590", "rsc": 2004, "rqi": "266f72d0",
               "rvi": "5", "drt": 1,
               "pc": {"m2m:cnt": {"rn": "temp", "mni": 100, "cni": 1, "cbs": 4, "st": 2, "pi": "Cprobe",
                                  "ri": "cnt5OY01h7geE", "ty": 3, "ct": "20261110T214309,627055",
                                  "lt": "20261110T214311,208053", "et": "20311109T214309,617978",
                                  "lbl": ["room:lab"]}}}
NOT_FOUND = {"fr": "/id-in", "to": "Cprobe", "ot": "20261110T214309,604750", "rsc": 4004, "rqi": "87a4748e",
             "rvi": "5", "drt": 1, "pc": {"m2m:dbg": "No resource with this ID: cse-in/probeAE"}}
DELETED = {"fr": "/id-in", "to": "Cprobe", "ot": "20261110T214311,229984", "rsc": 2002, "rqi": "9efaae03",
           "rvi": "5", "drt": 1}

ALL = {name: value for name, value in globals().items() if name.isupper() and isinstance(value, dict)}
