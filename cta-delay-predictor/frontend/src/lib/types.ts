export type DelayStatus = "ahead" | "on_time" | "behind" | null;

export interface ArrivalItem {
  run_number: string;
  route: string;
  direction: string | null;
  destination: string | null;
  scheduled_time: string | null;
  cta_eta: string | null;
  cta_eta_minutes: number | null;
  model_delay_minutes: number | null;
  model_eta: string | null;
  delay_status: DelayStatus;
  p10_minutes: number | null;
  p90_minutes: number | null;
  is_delayed: boolean;
  is_scheduled: boolean;
  is_approaching: boolean;
}

export interface StationArrivalsResponse {
  station_id: string;
  station_name: string | null;
  route: string;
  as_of: string;
  arrivals: ArrivalItem[];
}

export interface Station {
  mapid: number;
  name: string;
  route: "Red" | "Blue";
  branch?: string;
}

// Static station list mirrored from backend/stations.py
export const RED_LINE_STATIONS: Station[] = [
  { mapid: 40900, name: "Howard", route: "Red" },
  { mapid: 41190, name: "Jarvis", route: "Red" },
  { mapid: 40100, name: "Morse", route: "Red" },
  { mapid: 41300, name: "Loyola", route: "Red" },
  { mapid: 40760, name: "Granville", route: "Red" },
  { mapid: 40880, name: "Thorndale", route: "Red" },
  { mapid: 41380, name: "Bryn Mawr", route: "Red" },
  { mapid: 40340, name: "Berwyn", route: "Red" },
  { mapid: 41200, name: "Argyle", route: "Red" },
  { mapid: 40540, name: "Wilson", route: "Red" },
  { mapid: 40080, name: "Sheridan", route: "Red" },
  { mapid: 41420, name: "Addison", route: "Red" },
  { mapid: 41320, name: "Belmont", route: "Red" },
  { mapid: 41220, name: "Fullerton", route: "Red" },
  { mapid: 40650, name: "North/Clybourn", route: "Red" },
  { mapid: 40630, name: "Clark/Division", route: "Red" },
  { mapid: 41450, name: "Chicago", route: "Red" },
  { mapid: 40330, name: "Grand", route: "Red" },
  { mapid: 41660, name: "Lake", route: "Red" },
  { mapid: 41090, name: "Monroe", route: "Red" },
  { mapid: 40560, name: "Jackson", route: "Red" },
  { mapid: 41490, name: "Harrison", route: "Red" },
  { mapid: 41000, name: "Cermak-Chinatown", route: "Red" },
  { mapid: 40190, name: "Sox-35th", route: "Red" },
  { mapid: 41230, name: "47th", route: "Red" },
  { mapid: 41170, name: "Garfield", route: "Red" },
  { mapid: 40910, name: "63rd", route: "Red" },
  { mapid: 40990, name: "69th", route: "Red" },
  { mapid: 40240, name: "79th", route: "Red" },
  { mapid: 41430, name: "87th", route: "Red" },
  { mapid: 40450, name: "95th/Dan Ryan", route: "Red" },
];

export const BLUE_LINE_STATIONS: Station[] = [
  { mapid: 40890, name: "O'Hare", route: "Blue", branch: "ohare" },
  { mapid: 40820, name: "Rosemont", route: "Blue", branch: "ohare" },
  { mapid: 40230, name: "Cumberland", route: "Blue", branch: "ohare" },
  { mapid: 40750, name: "Harlem (O'Hare)", route: "Blue", branch: "ohare" },
  { mapid: 41280, name: "Jefferson Park", route: "Blue", branch: "ohare" },
  { mapid: 41330, name: "Montrose", route: "Blue", branch: "ohare" },
  { mapid: 40550, name: "Irving Park", route: "Blue", branch: "ohare" },
  { mapid: 41240, name: "Addison", route: "Blue", branch: "ohare" },
  { mapid: 40060, name: "Belmont", route: "Blue", branch: "ohare" },
  { mapid: 41020, name: "Logan Square", route: "Blue", branch: "ohare" },
  { mapid: 40570, name: "California", route: "Blue", branch: "ohare" },
  { mapid: 40670, name: "Western (O'Hare)", route: "Blue", branch: "ohare" },
  { mapid: 40590, name: "Damen", route: "Blue", branch: "ohare" },
  { mapid: 40320, name: "Division", route: "Blue" },
  { mapid: 41410, name: "Chicago", route: "Blue" },
  { mapid: 40490, name: "Grand", route: "Blue" },
  { mapid: 40380, name: "Clark/Lake", route: "Blue" },
  { mapid: 40370, name: "Washington", route: "Blue" },
  { mapid: 40790, name: "Monroe", route: "Blue" },
  { mapid: 41340, name: "Jackson", route: "Blue" },
  { mapid: 40430, name: "LaSalle", route: "Blue", branch: "forest_park" },
  { mapid: 40390, name: "Clinton", route: "Blue", branch: "forest_park" },
  { mapid: 40350, name: "UIC-Halsted", route: "Blue", branch: "forest_park" },
  { mapid: 40470, name: "Racine", route: "Blue", branch: "forest_park" },
  { mapid: 40810, name: "Illinois Medical District", route: "Blue", branch: "forest_park" },
  { mapid: 40220, name: "Western (Forest Park)", route: "Blue", branch: "forest_park" },
  { mapid: 40250, name: "Kedzie-Homan", route: "Blue", branch: "forest_park" },
  { mapid: 40920, name: "Pulaski", route: "Blue", branch: "forest_park" },
  { mapid: 40970, name: "Cicero", route: "Blue", branch: "forest_park" },
  { mapid: 40010, name: "Austin", route: "Blue", branch: "forest_park" },
  { mapid: 40180, name: "Oak Park", route: "Blue", branch: "forest_park" },
  { mapid: 40980, name: "Harlem/Lake", route: "Blue", branch: "forest_park" },
];
