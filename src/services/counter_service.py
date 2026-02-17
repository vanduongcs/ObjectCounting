# services/counter_service.py


class CounterService:
    def __init__(self, region_split_y: int, buffer: int = 50):
        self.region_split_y = region_split_y
        self.buffer = buffer

        self.object_states = {}      # id -> last_region
        self.count_nhap = {}         # label -> int
        self.count_xuat = {}         # label -> int

    def _get_region(self, cy: float):
        upper_bound = self.region_split_y - self.buffer
        lower_bound = self.region_split_y + self.buffer

        if cy < upper_bound:
            return "NHAP"
        elif cy > lower_bound:
            return "XUAT"
        else:
            return "BUFFER"

    def update(self, detections):
        for obj in detections:
            obj_id = obj["id"]
            label = obj["label"]
            _, cy = obj["center"]

            current_region = self._get_region(cy)

            if current_region == "BUFFER":
                continue

            if obj_id not in self.object_states:
                self.object_states[obj_id] = current_region
                continue

            previous_region = self.object_states[obj_id]

            if previous_region != current_region:

                # NHAP -> XUAT  (xuất hàng)
                if previous_region == "NHAP" and current_region == "XUAT":
                    if self.count_nhap.get(label, 0) == 0:
                        self.count_xuat[label] = self.count_xuat.get(label, 0) + 1
                    else:
                        self.count_nhap[label] -= 1

                # XUAT -> NHAP (nhập hàng)
                elif previous_region == "XUAT" and current_region == "NHAP":
                    self.count_nhap[label] = self.count_nhap.get(label, 0) + 1

                self.object_states[obj_id] = current_region

    def get_counts(self):
        return self.count_nhap, self.count_xuat
