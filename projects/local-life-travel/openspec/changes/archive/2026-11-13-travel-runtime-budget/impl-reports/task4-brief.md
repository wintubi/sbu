### Task 4: 实现验证（聚合收尾）

**Blocked-by:** 1,2,3
**R-ID:** all

按聚合套件发现契约运行本change命中域的全部层。此票唯一且不计入三张功能切片预算；承担原任务3.3，不增加产品范围。

- [ ] 起手运行权威suite-scope并将base/head/domains_configured/hit_domains/layers/skipped_layers/mapping的JSON管道直贴报告头，不手工转录、不解析构建文件猜套件。
- [ ] 命中域各层证据齐全并通过，或按契约记录未覆盖/不在命中域；记录真实命令、退出码与实际用例数，零用例不算通过，不用票内局部测试代替全部聚合层。
- [ ] 完整pytest覆盖既有replay、Amap离线与LIVE场景及新增运行边界；真实loopback聚合流程有可复现证据；未运行/失败/真实供应商与生产未验范围明确保留，不以全绿推出硬中断、灾备或供应商效果。
