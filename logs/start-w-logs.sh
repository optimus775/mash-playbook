# Чистый вывод в файл
ANSIBLE_LOG_PATH=logs/install-all-$(date +%F_%H-%M).log just install-all

# С выводом и в файл и в лог
ANSIBLE_LOG_PATH=logs/install-all-$(date +%F_%H-%M).log just install-all |& tee -a logs/install-all-$(date +%F_%H-%M).log

