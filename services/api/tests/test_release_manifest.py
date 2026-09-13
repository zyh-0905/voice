"""W22 / §14.6 发布 manifest:记录的东西必须真的存在且对得上。

这份产物唯一的用处是**准确**。此前 `prompts` / `rules_version` / `test_data_hash`
三个字段写死 null,并附带一句「仓库里没有 prompts/ 与 rules 版本文件」——而那两个文件
一直都在。于是 manifest 声称「提示模板无版本」,而 §8.5 恰恰要求记录提示模板版本,
且每次命名都用它。null 与「真的没有」在这些字段上无法区分,所以要有闸门。
"""
from scripts.ops_common import REPO_ROOT
from scripts.release_manifest import build_manifest


def _manifest():
    return build_manifest()


def test_prompt_files_are_recorded_with_hashes():
    prompts = _manifest()['prompts']
    assert prompts['files'], '提示模板文件一个都没记到'
    for item in prompts['files']:
        path = REPO_ROOT / item['file']
        assert path.is_file(), f"manifest 引用了不存在的文件: {item['file']}"
        assert item['sha256'] and len(item['sha256']) == 64
    assert prompts['combined_sha256']


def test_rules_policy_records_its_own_version_id():
    """规则集带自己的 `policy_id`(8.4),而它会随产物落库,manifest 必须记同一份。"""
    rules = _manifest()['rules_version']
    assert rules['policy_id'], '规则集没有记到 policy_id'
    assert (REPO_ROOT / rules['file']).is_file()
    assert rules['sha256']


def test_test_data_is_recorded():
    data = _manifest()['test_data']
    assert data['file'] and data['sha256']
    assert (REPO_ROOT / data['file']).is_file()


def test_prompt_hash_matches_what_the_provider_loads():
    """manifest 记的提示词,必须就是对外调用时真正发出去的那一份。

    两处各读一次文件、各算一次 hash 的话,改了文件而 manifest 没重跑,就会得到
    「记录的是 A、发出去的是 B」——而这份产物正是用来回答「这一版用的是哪份提示词」。
    """
    from app.topic_provider import load_system_prompt
    from scripts.release_manifest import sha256_file_join

    recorded = _manifest()['prompts']['files'][0]
    path = REPO_ROOT / recorded['file']

    assert load_system_prompt() == path.read_text(encoding='utf-8').strip()
    assert recorded['sha256'] == sha256_file_join([path])


def test_known_gaps_do_not_claim_files_are_missing():
    """缺口清单只能写真实缺口。

    此前它写着「prompts/ 与固定合成测试数据集不存在」——那是陈旧的臆断,而被它
    影响的人会据此以为提示词不受版本控制。
    """
    gaps = ' '.join(_manifest()['known_gaps'])
    assert '不存在' not in gaps, f'缺口清单在声称文件不存在: {gaps}'
