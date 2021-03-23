---
title:  "Headless Testing in PySide2"
categories: 
  - Jekyll
tags:
  - update
---

For my first post, I will be discussing something that I've had to deal with for quite some time now: writing Python unit tests for a GUI written in Qt.

### Article Datasheet

| Name | Version |
| ------ | ------ |
| Python | 3.6.8 |
| PySide2 | 5.14.1 |

### Introduction
Let's say you had an application written in Python, but you need a graphical interface. One that is portable, easy to deploy, and well documented. It would not be too surprising if you ended up opting for Qt, as they operate a very well established, documented, and extensible C++ GUI framework which–since 2016–also had an officially supported set of Python bindings ([PySide2](https://wiki.qt.io/Qt_for_Python)). 

```python
def print_hi(name):
  print("Hi, {name}".format(name=name))

print_hi('Tom')
# prints 'Hi, Tom' to STDOUT.
```

Check out the [Jekyll docs][jekyll-docs] for more info on how to get the most out of Jekyll. File all bugs/feature requests at [Jekyll's GitHub repo][jekyll-gh]. If you have questions, you can ask them on [Jekyll Talk][jekyll-talk].

[jekyll-docs]: http://jekyllrb.com/docs/home
[jekyll-gh]:   https://github.com/jekyll/jekyll
[jekyll-talk]: https://talk.jekyllrb.com/