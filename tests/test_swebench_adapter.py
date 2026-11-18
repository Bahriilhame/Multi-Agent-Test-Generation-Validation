from experiments.swebench import public_instance


def test_public_swebench_instance_excludes_gold_patches():
    instance = {
        "instance_id": "django__django-1",
        "repo": "django/django",
        "base_commit": "0123456789abcdef",
        "problem_statement": "An observed defect",
        "patch": "gold production fix",
        "test_patch": "gold tests",
    }
    public = public_instance(instance)
    assert public["instance_id"] == "django__django-1"
    assert public["problem_statement"] == "An observed defect"
    assert "patch" not in public
    assert "test_patch" not in public
