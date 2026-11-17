def setup(project, host_root, runner_data_dir, dry_run, timeout):
    return dict(component="generic", status="PLANNED" if dry_run else "PASS", reused=True,
                reason="Generic checks use existing runtimes; there are no profile tools to install.")
