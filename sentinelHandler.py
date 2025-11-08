from sentinelhub import SHConfig, BBox, CRS, SentinelHubRequest, MimeType, DataCollection, SentinelHubCatalog
import matplotlib.pyplot as plt
import numpy as np
import os

class SentinelImageFetcher:
    def __init__(
        self,
        instance_id: str,
        client_id: str,
        client_secret: str,
        bbox_coords: list,
        time_interval: tuple,
        cloud_cover: int = 10,
        resolution: tuple = (1024, 1024),
        data_folder: str = "satellites-scans"
    ):
        """
        Klasa do pobierania zdjęć Sentinel-2 z Sentinel Hub API.

        :param instance_id: ID instancji Sentinel Hub
        :param client_id: Client ID aplikacji
        :param client_secret: Client Secret aplikacji
        :param bbox_coords: Współrzędne [minx, miny, maxx, maxy] w WGS84
        :param time_interval: Zakres czasu (start, end)
        :param cloud_cover: Maksymalne dopuszczalne zachmurzenie w %
        :param resolution: Rozdzielczość obrazu (width, height)
        :param data_folder: Folder do zapisu danych
        """

        # =========================
        # Konfiguracja Sentinel Hub
        # =========================
        self.config = SHConfig()
        self.config.instance_id = instance_id
        self.config.sh_client_id = client_id
        self.config.sh_client_secret = client_secret

        if not self.config.instance_id or not self.config.sh_client_id or not self.config.sh_client_secret:
            raise ValueError("Uzupełnij dane konfiguracyjne Sentinel Hub")


        self.bbox = BBox(bbox=bbox_coords, crs=CRS.WGS84)
        self.time_interval = time_interval
        self.cloud_cover = cloud_cover
        self.resolution = resolution
        self.data_folder = data_folder

        # Evalscript RGB
        self.evalscript_rgb = """
        //VERSION=3
        function setup() {
            return {
                input: ["B04","B03","B02"],
                output: { bands: 3 }
            };
        }
        function evaluatePixel(sample) {
            return [sample.B04, sample.B03, sample.B02];
        }
        """

    def find_clear_scenes(self, limit=20):
        catalog = SentinelHubCatalog(config=self.config)

        filter_expr = f"eo:cloud_cover < {self.cloud_cover}"

        search_iterator = catalog.search(
            DataCollection.SENTINEL2_L2A,
            bbox=self.bbox,
            time=self.time_interval,
            filter=filter_expr,
            limit=limit
        )

        results = list(search_iterator)
        print(f"Znaleziono {len(results)} scen (<{self.cloud_cover}% chmur):")

        for r in results:
            p = r['properties']
            print(f"- {p['datetime']} → {p['eo:cloud_cover']}% chmur")

        return results


    def download_scenes(self, results, show_preview=True):
        for result in results:
            date = result['properties']['datetime'][:10]
            print(f" Pobieram scenę z {date}...")

            folder_for_date = os.path.join(self.data_folder, date)
            os.makedirs(folder_for_date, exist_ok=True)

            request = SentinelHubRequest(
                evalscript=self.evalscript_rgb,
                input_data=[
                    SentinelHubRequest.input_data(
                        data_collection=DataCollection.SENTINEL2_L2A,
                        time_interval=(date, date),
                        mosaicking_order='mostRecent'
                    )
                ],
                responses=[
                    SentinelHubRequest.output_response('default', MimeType.PNG)
                ],
                bbox=self.bbox,
                size=self.resolution,
                data_folder=folder_for_date,
                config=self.config
            )
            image = request.get_data(save_data=True)

            if image and show_preview:
                img_array = np.array(image[0])
                plt.imshow(img_array)
                plt.axis('off')
                plt.title(f"Scena z {date}")
                plt.show()

        print("\nWszystkie sceny zostały pobrane.")


# =========================================
# =========================================
if __name__ == "__main__":
    fetcher = SentinelImageFetcher(
        instance_id='7c638c92-216c-4658-8643-31a2a14c6390',
        client_id='31196ff3-6ba0-40cf-82b5-126041fd20b6',
        client_secret='nt4agQlR9TnBXf6oykIaaU0f9smMj4AH',
        bbox_coords=[16.95, 51.05, 17.15, 51.15],
        time_interval=('2025-05-01', '2025-11-01'),
        cloud_cover=10,
        resolution=(1024, 1024),
        data_folder='satellites-scans'
    )

    scenes = fetcher.find_clear_scenes(limit=10)
    fetcher.download_scenes(scenes, show_preview=True)
