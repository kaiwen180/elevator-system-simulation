from elevator_sim.app.code_view import VIEWS, code_views


def test_every_view_reads_a_core_function_and_lights_at_least_one_line_per_group():
    views = code_views()
    assert set(views) == set(VIEWS)
    for name, v in views.items():
        assert v["file"].startswith("core/"), name
        assert v["start"] >= 1
        for group, lines in v["groups"].items():
            assert lines, f"{name}.{group}"
            assert all(0 <= i < len(v["lines"]) for i in lines)


def test_each_floors_to_reach_branch_ends_on_its_own_return():
    v = code_views()["floors"]
    returns = [max(lines) for lines in v["groups"].values()]
    assert len(set(returns)) == 7
    assert all(v["lines"][i].strip().startswith("return") for i in returns)


def test_the_lines_are_the_code_as_it_is():
    v = code_views()["cost"]
    assert v["name"] == "LowestCost.incremental_cost"
    assert v["lines"][0].startswith("def incremental_cost(")
    assert v["lines"][v["groups"]["trial"][-1]].strip() == "return cost - without"
