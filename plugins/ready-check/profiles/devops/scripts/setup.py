def setup(project, host_root, runner_data_dir, dry_run, timeout):
    return dict(component="devops", status="PLANNED" if dry_run else "PASS", reused=True,
                reason="DevOps uses tools from the selected environment. Run doctor for applicable prerequisites.")
