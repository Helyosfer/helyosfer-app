import unittest


class DashboardChartCacheTest(unittest.TestCase):
    def setUp(self):
        import services.asset_service as asset_service

        self.asset_service = asset_service
        self.original_revision = asset_service._financial_data_revision
        self.original_cache = asset_service._asset_data_cache
        self.original_stale = asset_service._account_cache_stale
        self.original_generation = asset_service._warmup_generation
        asset_service._financial_data_revision = 0

    def tearDown(self):
        self.asset_service._financial_data_revision = self.original_revision
        self.asset_service._asset_data_cache = self.original_cache
        self.asset_service._account_cache_stale = self.original_stale
        self.asset_service._warmup_generation = self.original_generation

    def test_balance_mutation_changes_chart_cache_key(self):
        before = self.asset_service.financial_chart_cache_key("Bugün")
        self.asset_service.mark_account_cache_stale()
        after = self.asset_service.financial_chart_cache_key("Bugün")

        self.assertNotEqual(before, after)

    def test_account_cache_invalidation_changes_chart_cache_key(self):
        before = self.asset_service.financial_chart_cache_key("1 Ay")
        self.asset_service.invalidate_asset_data_cache()
        after = self.asset_service.financial_chart_cache_key("1 Ay")

        self.assertNotEqual(before, after)







if __name__ == "__main__":
    unittest.main()
