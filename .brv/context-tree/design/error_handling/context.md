
Error handling: ValidationError/ValueError -> warning + UI message + signal; FileNotFoundError -> warning + signal; others -> critical + signal + logger.exception.
