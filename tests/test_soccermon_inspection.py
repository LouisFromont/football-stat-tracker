"""Selection and extraction guard regression tests; no canonical importer."""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import prepare_soccermon_subset as preparation
sys.path.pop(0)


class SubsetPreparationTests(unittest.TestCase):
    def entries(self, players):
        return [{'path':f'2020/2020-06/2020-06-{d:02d}/2020-06-{d:02d}-TeamB-{p}.parquet',
                 'extension':'.parquet','is_directory':False,'size_bytes':100}
                for d,ps in enumerate(players,1) for p in ps]

    def test_core_is_invariant_to_archive_order(self):
        entries=self.entries([['a','b','c','d']]*11)
        result=preparation.select(entries)
        self.assertEqual(result,preparation.select(list(reversed(entries))))
        self.assertEqual(result['date_indices'],[1,5,9])
        self.assertEqual(len(result['sessions']),9)
        self.assertEqual(len(result['selected_common_players']),3)

    def test_fallback_keeps_all_repeated_players_without_duplicates(self):
        entries=self.entries([['a','b','c'],['a','b','d'],['a','b','e']])
        result=preparation.select(entries)
        self.assertEqual(result['common_player_count'],2)
        self.assertEqual(len(result['sessions']),9)
        self.assertEqual(len({e['path'] for e in result['sessions']}),9)
        for day in result['selected_dates']:
            self.assertTrue({'a','b'}.issubset({e['player_filename_id'] for e in result['sessions'] if e['date']==day}))

    def test_ambiguous_player_filename_stops(self):
        entries=self.entries([['a','a'],['b'],['c']])
        with self.assertRaises(ValueError):
            preparation.select(entries)

    def test_budget_and_free_space_are_checked_before_extraction(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with self.assertRaises(ValueError):
                preparation.check_budget({'selected_size_bytes':preparation.BUDGET+1},root)
            (root/'existing').write_bytes(b'raw')
            with self.assertRaises(ValueError):
                preparation.check_budget({'selected_size_bytes':preparation.BUDGET},root)
            with patch.object(preparation.shutil,'disk_usage') as usage:
                usage.return_value.free=1
                with self.assertRaises(OSError):
                    preparation.check_budget({'selected_size_bytes':100},root)
            self.assertEqual((root/'existing').read_bytes(),b'raw')

    def test_inventory_includes_machine_readable_member_details(self):
        import zipfile
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'sample.zip'
            with zipfile.ZipFile(path,'w') as archive:
                archive.writestr('2020/example.parquet',b'abc')
            entry=preparation.inspect_zip(path)['entries'][0]
            self.assertEqual(entry['path'],'2020/example.parquet')
            self.assertEqual(entry['size_bytes'],3)
            self.assertEqual(entry['extension'],'.parquet')
            self.assertEqual(len(entry['crc32']),8)
            self.assertIn('T',entry['zip_modified_local'])

if __name__=='__main__':
    unittest.main()
